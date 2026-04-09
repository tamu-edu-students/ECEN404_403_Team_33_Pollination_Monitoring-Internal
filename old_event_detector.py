"""
SICKSense Agripollinate LiDAR Event Logger Version 0.4
Created by: Josiah Faircloth
Modified by: Paavan Bagla
Flower background with foreground bee detection
"""

import socket
import json
import time
from datetime import datetime
import os

HOST = "169.254.251.84"
PORT = 2112

CMD_START = b"\x02sEN LMDscandata 1\x03"
CMD_STOP = b"\x02sEN LMDscandata 0\x03"

FLOWERS = {
    "flower_1": {
        "angle_indices": [76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88],
        "background_dist": 0.20
    },
    "flower_2": {
        "angle_indices": [163, 164, 165, 166, 167, 168, 169, 170],
        "background_dist": 0.31
    }

}

DIST_THRESHOLD = 0.035
START_CONFIRM_SCANS = 8
END_CONFIRM_SCANS = 8


def parse_scan(telegram):
    parts = telegram.strip().split(" ")
    if "DIST1" not in parts:
        return None

    try:
        idx = parts.index("DIST1") + 5
        count = int(parts[idx], 16)

        return [
            int(v, 16) / 1000.0
            for v in parts[idx + 1 : idx + 1 + count]
        ]
    except Exception:
        return None


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    raw_dataset_folder = os.path.join(script_dir, "lidar_ML/dataset", "raw_dataset")
    os.makedirs(raw_dataset_folder, exist_ok=True)

    flower_state = {
        fid: {
            "active": False,
            "start_time": None,
            "start_count": 0,
            "end_count": 0,
            "distance_series": []
        }
        for fid in FLOWERS
    }

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(CMD_START)

        print("Connected to LiDAR")
        print("Monitoring flower occupancy")
        print("Press Ctrl C to stop\n")

        buffer = ""
        scan_id = 0

        try:
            while True:
                data = s.recv(4096).decode(errors="ignore")
                buffer += data

                while "\x03" in buffer:
                    telegram, buffer = buffer.split("\x03", 1)
                    telegram = telegram.replace("\x02", "").strip()

                    distances = parse_scan(telegram)
                    if not distances:
                        continue

                    scan_id += 1
                    scan_time = time.time()

                    for fid, cfg in FLOWERS.items():
                        indices = cfg["angle_indices"]
                        bg = cfg["background_dist"]

                        flower_ranges = [distances[i] for i in indices]
                        min_dist = min(flower_ranges)

                        occupied = min_dist < (bg - DIST_THRESHOLD)
                        state = flower_state[fid]

                        print(
                            f"Scan {scan_id} | {fid} | "
                            f"min_dist {min_dist:.2f} m | "
                            f"occupied {occupied}"
                        )
                        # -----------------------------
                        # EVENT START DETECTION
                        # -----------------------------
                        if not state["active"]:
                            if occupied:
                                state["start_count"] += 1
                                print(
                                    f"  start_count {state['start_count']}/"
                                    f"{START_CONFIRM_SCANS}"
                                )

                                if state["start_count"] >= START_CONFIRM_SCANS:
                                    state["active"] = True
                                    state["start_time"] = scan_time
                                    state["distance_series"] = []
                                    state["end_count"] = 0
                                    print(f"  EVENT STARTED for {fid}")
                            else:
                                state["start_count"] = 0
                        # -----------------------------
                        # EVENT END DETECTION
                        # -----------------------------
                        else:
                            state["distance_series"].append(flower_ranges)

                            if not occupied:
                                state["end_count"] += 1
                                print(
                                    f"  end_count {state['end_count']}/"
                                    f"{END_CONFIRM_SCANS}"
                                )

                                if state["end_count"] >= END_CONFIRM_SCANS:
                                    event_id = f"{fid}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                                    timestamp = datetime.now().isoformat()

                                    event = {
                                        "event_type": "flower_visit",
                                        "event_id": event_id,
                                        "flower_id": fid,
                                        "background_dist": bg,
                                        "start_time": state["start_time"],
                                        "end_time": scan_time,
                                        "num_scans": len(state["distance_series"]),
                                        "angles": indices,
                                        "distance_series": state["distance_series"],
                                        "timestamp": timestamp,
                                        "label": None
                                    }
                                    # Unique filename
                                    filename = f"{event_id}.json"
                                    filepath = os.path.join(raw_dataset_folder, filename)

                                    # Save JSON file
                                    with open(filepath, "w") as event_file:
                                        json.dump(event, event_file, indent=4)

                                    print(f"  EVENT ENDED for {fid}\n")

                                    state["active"] = False
                                    state["start_time"] = None
                                    state["start_count"] = 0
                                    state["end_count"] = 0
                                    state["distance_series"] = []
                            else:
                                state["end_count"] = 0

        except KeyboardInterrupt:
            print("\nStopping stream")

        finally:
            s.sendall(CMD_STOP)
            print(f"Session complete. Events saved in {raw_dataset_folder}")

if __name__ == "__main__":
    main()