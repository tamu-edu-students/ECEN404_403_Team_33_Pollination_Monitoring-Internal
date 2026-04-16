import socket
import json
from datetime import datetime
import statistics
import os

HOST = "169.254.251.84"
PORT = 2112

CMD_START = b"\x02sEN LMDscandata 1\x03"
CMD_STOP = b"\x02sEN LMDscandata 0\x03"

NUM_BASELINE_SCANS = 100
MAX_PLANT_DIST = 0.5  # meters

# Spatial clustering parameters
MIN_BLOCK_SIZE = 3
MAX_BLOCK_SIZE = 25
MAX_DIST_STD = 0.08

# Temporal persistence parameters
ANGLE_TOLERANCE = 5  # degrees, for matching clusters across scans
DIST_TOLERANCE = 0.15
MIN_HITS = 20


def parse_scan(telegram):
    """
    Extract distance array from LiDAR telegram.
    """
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

def extract_clusters_from_scan(distances):
    """
    Phase 1: spatial clustering for one scan.
    Groups contiguous indices ONLY if distance is similar and within working range.
    """
    clusters = []
    if not distances:
        return clusters
        
    current_block = [0]
    
    for i in range(1, len(distances)):
        # Check if the next point is physically close to the previous one
        if abs(distances[i] - distances[i - 1]) <= MAX_DIST_STD:
            current_block.append(i)
        else:
            # Process the block we just finished
            process_potential_cluster(current_block, distances, clusters)
            current_block = [i]

    # Don't forget the last block in the scan
    process_potential_cluster(current_block, distances, clusters)

    return clusters

def process_potential_cluster(block, distances, cluster_list):
    """Helper to validate size and distance before adding to the list."""
    if MIN_BLOCK_SIZE <= len(block) <= MAX_BLOCK_SIZE:
        block_dists = [distances[j] for j in block]
        mean_dist = statistics.mean(block_dists)
        
        # WORKING RANGE FILTER:
        # This is the "cleanest place" to drop background vegetation
        if mean_dist <= MAX_PLANT_DIST:
            cluster_list.append({
                "indices": block,
                "angle_center": int(statistics.mean(block)),
                "mean_dist": round(mean_dist, 3)
            })

def main():
    timestamp = datetime.now().strftime("%m_%d_%Y_%H_%M_%S")
    if not os.path.exists('setup'):
            os.makedirs('setup')
    
    out_file = f"setup/flower_setup_{timestamp}.json"

    scans = []

    # -----------------------------
    # Collect scans
    # -----------------------------
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(CMD_START)

        print("Connected to LiDAR")
        print("Collecting scans.....")

        buffer = ""

        while len(scans) < NUM_BASELINE_SCANS:
            data = s.recv(4096).decode(errors="ignore")
            buffer += data

            while "\x03" in buffer and len(scans) < NUM_BASELINE_SCANS:
                telegram, buffer = buffer.split("\x03", 1)
                telegram = telegram.replace("\x02", "").strip()

                scan = parse_scan(telegram)
                if scan:
                    scans.append(scan)

        s.sendall(CMD_STOP)

    print(f"\nCollected {len(scans)} scans\n")

    # -----------------------------
    # Phase 2: temporal clustering
    # -----------------------------
    tracks = []

    for scan in scans:
        clusters = extract_clusters_from_scan(scan)

        for c in clusters:
            matched = False

            for track in tracks:
                if abs(c["angle_center"] - track["angle_center"]) <= ANGLE_TOLERANCE:
                    if abs(c["mean_dist"] - track["mean_dist"]) <= DIST_TOLERANCE:
                        track["hits"] += 1
                        track["all_indices"].append(c["indices"])
                        track["all_dists"].append(c["mean_dist"])
                        matched = True
                        break

            if not matched:
                tracks.append({
                    "angle_center": c["angle_center"],
                    "mean_dist": c["mean_dist"],
                    "hits": 1,
                    "all_indices": [c["indices"]],
                    "all_dists": [c["mean_dist"]]
                })

    # -----------------------------
    # Final flower selection
    # -----------------------------
    flower_config = {}
    flower_id = 1

    for track in tracks:
        if track["hits"] < MIN_HITS:
            continue

        merged_indices = sorted(
            set(i for block in track["all_indices"] for i in block)
        )

        mean_dist = statistics.mean(track["all_dists"])
        bg = round(mean_dist, 3)

        if bg == 0.0:
            continue

        flower_config[f"flower_{flower_id}"] = {
            "angle_indices": merged_indices,
            "background_dist": round(mean_dist, 3)
        }

        print(f"Flower {flower_id}")
        print(f"Indices {merged_indices}")
        print(f"Distance {mean_dist:.2f} m\n")

        flower_id += 1

    with open(out_file, "w") as f:
        json.dump(flower_config, f, indent=2)

    print(f"Saved flower configuration to {out_file}")


if __name__ == "__main__":
    main()
