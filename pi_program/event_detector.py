"""
SICKSense Agripollinate LiDAR Event Logger Version 0.4
Created by: Josiah Faircloth
Modified by: Paavan Bagla
Flower background with foreground bee detection

EventDetector class for real-time flower visit detection from LiDAR scans.
"""

import socket
import json
import time
from datetime import datetime


class EventDetector:
    """
    Detects flower visit events from LiDAR scan data.
    Triggers callbacks when events start and end.
    """
    
    def __init__(self, 
                 flowers=None,
                 dist_threshold=0.035,
                 start_confirm_scans=8,
                 end_confirm_scans=8):
        """
        Initialize event detector with flower configuration.
        
        Args:
            flowers: Dictionary of flower configurations with angle_indices and background_dist
            dist_threshold: Distance threshold for occupancy detection (meters)
            start_confirm_scans: Number of consecutive scans to confirm event start
            end_confirm_scans: Number of consecutive scans to confirm event end
        """
        if flowers is None:
            self.flowers = {
                "flower_1": {
                    "angle_indices": [68, 69, 70, 71],
                    "background_dist": 0.269
                },
                "flower_2": {
                    "angle_indices": [168, 169, 170, 171],
                    "background_dist": 0.34
                }
            }
        else:
            self.flowers = flowers
        
        self.dist_threshold = dist_threshold
        self.start_confirm_scans = start_confirm_scans
        self.end_confirm_scans = end_confirm_scans

        # Detection tuning knobs.
        # - weak_residual: minimum per-angle drop to count as small-object evidence
        # - start_evidence_threshold: stronger evidence needed to begin an event
        # - end_evidence_threshold: lower threshold to keep event active (hysteresis)
        self.weak_residual = max(0.006, self.dist_threshold * 0.20)
        self.start_evidence_threshold = max(0.012, self.dist_threshold * 0.75)
        self.end_evidence_threshold = max(0.008, self.start_evidence_threshold * 0.60)
        self.baseline_learning_rate = 0.02
        self.min_strong_scans_to_start = max(1, self.start_confirm_scans // 3)
        
        # Initialize flower state
        self.flower_state = {
            fid: {
                "active": False,
                "start_time": None,
                "start_count": 0,
                "strong_count": 0,
                "end_count": 0,
                "distance_series": [],
                "threshold": cfg["background_dist"] - self.dist_threshold,
                "prev_occupied": False,
                # Per-angle baseline profile; defaults to flower background distance.
                "baseline_map": {
                    idx: cfg.get("baseline_by_angle", {}).get(idx, cfg["background_dist"])
                    for idx in cfg["angle_indices"]
                },
                # Adjacent-angle rule support: allows persistent single-angle weak hits.
                "single_hit_streak": 0
            }
            for fid, cfg in self.flowers.items()
        }
        
        self.scan_id = 0
        self.buffer = ""

################################################1
    def _compute_evidence(self, distances, indices, baseline_map):
        """
        Build residual evidence against per-angle baselines.
        Returns (evidence_score, residuals, hit_indices).
        """
        residuals = {
            idx: max(0.0, baseline_map[idx] - distances[idx])
            for idx in indices
        }

        # Accumulate only residual above weak floor to suppress tiny jitter noise.
        evidence = sum(max(0.0, residuals[idx] - self.weak_residual) for idx in indices)
        hit_indices = [idx for idx in indices if residuals[idx] > self.weak_residual]
        return evidence, residuals, hit_indices

    def _adjacent_rule_passes(self, state, hit_indices):
        """
        Require either adjacent-angle hits or persistent single-angle hits.
        """
        sorted_hits = sorted(hit_indices)
        adjacent_pair = any((b - a) == 1 for a, b in zip(sorted_hits, sorted_hits[1:]))

        if len(sorted_hits) == 1:
            state["single_hit_streak"] += 1
        else:
            state["single_hit_streak"] = 0

        return adjacent_pair or state["single_hit_streak"] >= 2

    def _update_baseline(self, state, indices, distances):
        """
        Slowly adapt baselines only when not in an active event.
        This tracks gradual flower/environment drift without learning the bee.
        """
        for idx in indices:
            base = state["baseline_map"][idx]
            state["baseline_map"][idx] = ((1.0 - self.baseline_learning_rate) * base
                                          + self.baseline_learning_rate * distances[idx])
    ################################################1

    def detect_events(self, distances, scan_time):
        """
        Process a LiDAR scan and detect flower visit events.
        
        Args:
            distances: Array of distance measurements from LiDAR scan
            scan_time: Timestamp of the scan
            
        Returns:
            List of events that were triggered. Each event is a dict with:
            - 'type': 'start' or 'end'
            - 'flower_id': ID of the flower
            - 'start_time': Timestamp when event started
            - 'end_time': Timestamp when event ended (for end events)
            - 'distance_series': List of distance readings during visit (for end events)
            - 'angles': Angle indices for the flower
        """
        triggered_events = []
        
        for fid, cfg in self.flowers.items():
            indices = cfg["angle_indices"]
            state = self.flower_state[fid]
            #######################################2

            # Compute residual evidence from per-angle baselines.
            evidence, residuals, hit_indices = self._compute_evidence(
                distances, indices, state["baseline_map"]
            )

            # Adjacent-angle rule (or persistent single-angle weak hit) for small-object support.
            adjacent_ok = self._adjacent_rule_passes(state, hit_indices)

            # Two-stage candidate/strong logic for event start.
            candidate_present = evidence >= self.end_evidence_threshold and adjacent_ok
            strong_present = evidence >= self.start_evidence_threshold

            # Hysteresis keeps active events stable with a lower hold threshold.
            occupied = candidate_present if not state["active"] else evidence >= self.end_evidence_threshold

            # Update baseline only when idle and no current occupancy evidence.
            if not state["active"] and not occupied:
                self._update_baseline(state, indices, distances)

            #######################################2
            min_dist = min(distances[i] for i in indices)

            if occupied != state["prev_occupied"]:
                print(
                    f"Scan {self.scan_id} | {fid} | "
                    f"STATUS CHANGE | "
                    f"min_dist {min_dist:.2f} m | evidence {evidence:.3f} | "
                    f"occupied {occupied}"
                )
                state["prev_occupied"] = occupied

            if not state["active"]:
                if candidate_present:
                    state["start_count"] += 1
                    if strong_present:
                        state["strong_count"] += 1
                    print(
                        f"  start_count {state['start_count']}/"
                        f"{self.start_confirm_scans}"
                    )

                    if (state["start_count"] >= self.start_confirm_scans
                            and state["strong_count"] >= self.min_strong_scans_to_start):
                        # Event start triggered
                        state["active"] = True
                        state["start_time"] = scan_time
                        state["distance_series"] = []
                        state["end_count"] = 0
                        state["strong_count"] = 0
                        '''print(f"  EVENT STARTED for {fid}")'''
                        
                        triggered_events.append({
                            "type": "start",
                            "flower_id": fid,
                            "start_time": scan_time,
                            "angles": indices
                        })
                else:
                    state["start_count"] = 0
                    state["strong_count"] = 0
            else:
                state["distance_series"].append([distances[i] for i in indices])

                if not occupied:
                    state["end_count"] += 1
                    '''print(
                        f"  end_count {state['end_count']}/"
                        f"{self.end_confirm_scans}"
                    )'''

                    if state["end_count"] >= self.end_confirm_scans:
                        # Event end triggered - prepare data for transmission
                        event_id = f"{fid}_{state['start_time']:.2f}"
                        
                        bg = cfg["background_dist"]
                        event = {
                            "type": "end",
                            "event_type": "flower_visit",
                            "event_id": event_id,
                            "flower_id": fid,
                            "background_dist": bg,
                            "start_time": state["start_time"],
                            "end_time": scan_time,
                            "num_scans": len(state["distance_series"]),
                            "angles": indices,
                            "distance_series": state["distance_series"],
                            "timestamp": scan_time,
                            "label": None
                        }
                        '''print(f"  EVENT ENDED for {fid}\n")'''

                        state["active"] = False
                        state["start_time"] = None
                        state["start_count"] = 0
                        state["strong_count"] = 0
                        state["end_count"] = 0
                        state["distance_series"] = []
                        state["single_hit_streak"] = 0
                        
                        triggered_events.append(event)
                else:
                    state["end_count"] = 0
        
        self.scan_id += 1
        return triggered_events
