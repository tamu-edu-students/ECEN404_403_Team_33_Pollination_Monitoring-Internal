# quick_check.py — run from lidar_ML directory
import os, json, statistics

TEST_PATH = "dataset/test_dataset"   # adjust to your path

for filename in sorted(os.listdir(TEST_PATH)):
    if not filename.endswith(".json"): continue
    with open(os.path.join(TEST_PATH, filename)) as f:
        event = json.load(f)
    
    label    = event.get("label", "?")
    duration = event["end_time"] - event["start_time"]
    bg       = event.get("background_dist", 0.3)
    num_scans = event["num_scans"]
    
    mid_start = num_scans // 5
    mid_end   = num_scans - num_scans // 5
    mid_scans = event["distance_series"][mid_start:mid_end]
    mid_mins  = [min(s) for s in mid_scans] if mid_scans else [0]
    movement  = statistics.stdev(mid_mins) if len(mid_mins) > 1 else 0

    print(f"{label:<10} dur={duration:.2f}s  movement={movement:.5f}")