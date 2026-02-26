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
        
        # Initialize flower state
        self.flower_state = {
            fid: {
                "active": False,
                "start_time": None,
                "start_count": 0,
                "end_count": 0,
                "distance_series": [],
                "threshold": cfg["background_dist"] - self.dist_threshold,
                "prev_occupied": False
            }
            for fid, cfg in self.flowers.items()
        }
        
        self.scan_id = 0
        self.buffer = ""
    
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

            min_dist = min(distances[i] for i in indices)

            state = self.flower_state[fid]
            occupied = min_dist < state["threshold"]

            if occupied != state["prev_occupied"]:
                print(
                    f"Scan {self.scan_id} | {fid} | "
                    f"STATUS CHANGE | "
                    f"min_dist {min_dist:.2f} m | "
                    f"occupied {occupied}"
                )
                state["prev_occupied"] = occupied

            if not state["active"]:
                if occupied:
                    state["start_count"] += 1
                    print(
                        f"  start_count {state['start_count']}/"
                        f"{self.start_confirm_scans}"
                    )

                    if state["start_count"] >= self.start_confirm_scans:
                        # Event start triggered
                        state["active"] = True
                        state["start_time"] = scan_time
                        state["distance_series"] = []
                        state["end_count"] = 0
                        '''print(f"  EVENT STARTED for {fid}")'''
                        
                        triggered_events.append({
                            "type": "start",
                            "flower_id": fid,
                            "start_time": scan_time,
                            "angles": indices
                        })
                else:
                    state["start_count"] = 0
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
                        event = {
                            "type": "end",
                            "event_type": "flower_visit",
                            "flower_id": fid,
                            "start_time": state["start_time"],
                            "end_time": scan_time,
                            "num_scans": len(state["distance_series"]),
                            "angles": indices,
                            "distance_series": state["distance_series"]
                        }

                        '''print(f"  EVENT ENDED for {fid}\n")'''

                        state["active"] = False
                        state["start_time"] = None
                        state["start_count"] = 0
                        state["end_count"] = 0
                        state["distance_series"] = []
                        
                        triggered_events.append(event)
                else:
                    state["end_count"] = 0
        
        self.scan_id += 1
        return triggered_events
