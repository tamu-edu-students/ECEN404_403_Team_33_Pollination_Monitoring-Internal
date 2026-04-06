import socket
import json
from datetime import datetime
import statistics
import os
import math

HOST = "169.254.251.84"
PORT = 2112

CMD_START = b"\x02sEN LMDscandata 1\x03"
CMD_STOP = b"\x02sEN LMDscandata 0\x03"

NUM_BASELINE_SCANS = 50  # Updated to 50 for background capture
NUM_FLOWER_SCANS = 50    # 50 scans for detection
MAX_PLANT_DIST = 0.5     # meters
DETECTION_THRESHOLD = 0.1 # meters (how much closer an object must be than baseline)

def parse_scan(telegram):
    """Extract distance array from LiDAR telegram."""
    parts = telegram.strip().split(" ")
    if "DIST1" not in parts:
        return None
    try:
        idx = parts.index("DIST1") + 5
        count = int(parts[idx], 16)
        return [int(v, 16) / 1000.0 for v in parts[idx + 1 : idx + 1 + count]]
    except Exception:
        return None

def collect_scans(sock, target_count):
    """Helper to collect a specific number of scans from the LiDAR."""
    scans = []
    buffer = ""
    sock.sendall(CMD_START)
    while len(scans) < target_count:
        data = sock.recv(4096).decode(errors="ignore")
        buffer += data
        while "\x03" in buffer and len(scans) < target_count:
            telegram, buffer = buffer.split("\x03", 1)
            telegram = telegram.replace("\x02", "").strip()
            scan = parse_scan(telegram)
            if scan:
                scans.append(scan)
    sock.sendall(CMD_STOP)
    return scans

def main():
    timestamp = datetime.now().strftime("%m_%d_%Y_%H_%M_%S")
    if not os.path.exists('setup'):
        os.makedirs('setup')
    
    out_file = f"setup/flower_setup_{timestamp}.json"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        
        # 1. Capture Background Baseline
        print(f"Collecting {NUM_BASELINE_SCANS} background scans...")
        background_scans = collect_scans(s, NUM_BASELINE_SCANS)
        
        # Calculate baseline (average distance per index)
        num_points = len(background_scans[0])
        baseline = [statistics.mean([scan[i] for scan in background_scans]) for i in range(num_points)]

        # 2. Wait for User Input
        input("\nBackground environment scanned. Place the flowers and then press enter...")

        # 3. Capture Flower Scans
        print(f"Collecting {NUM_FLOWER_SCANS} scans with flowers...")
        flower_scans = collect_scans(s, NUM_FLOWER_SCANS)

    # 4. Process Scans to Detect Flowers
    # Average the 50 flower scans to reduce noise
    avg_flower_scan = [statistics.mean([scan[i] for scan in flower_scans]) for i in range(num_points)]

    detected_indices = []
    for i in range(num_points):
        # Detect points significantly closer than baseline and within MAX_PLANT_DIST
        if avg_flower_scan[i] < (baseline[i] - DETECTION_THRESHOLD) and avg_flower_scan[i] < MAX_PLANT_DIST:
            detected_indices.append(i)

    # Cluster adjacent indices into distinct flower objects
    flowers = []
    if detected_indices:
        current_cluster = [detected_indices[0]]
        for i in range(1, len(detected_indices)):
            if detected_indices[i] == detected_indices[i-1] + 1:
                current_cluster.append(detected_indices[i])
            else:
                flowers.append(current_cluster)
                current_cluster = [detected_indices[i]]
        flowers.append(current_cluster)

    # 5. Save and Output Results
    flower_config = {}
    flower_id = 1

    for indices in flowers:
        per_point_dists = [avg_flower_scan[idx] for idx in indices]

        flower_config[f"flower_{flower_id}"] = {
            "angle_indices": indices,
            "background_dist": [round(d, 3) for d in per_point_dists]
        }

        print(f"Flower {flower_id}: {len(indices)} points")
        print(f'Indices: {indices}')
        print(f'Distances: {[round(d, 3) for d in per_point_dists]}\n')

        flower_id += 1

    with open(out_file, "w") as f:
        json.dump(flower_config, f, indent=2)
    print(f"Saved flower configuration to {out_file}")

if __name__ == "__main__":
    main()