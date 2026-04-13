import os, json, statistics

TEST_PATH = "dataset/test_dataset"   # adjust to your path

# Updated header to include new metrics
print(f"{'FILE':<40} {'LABEL':<8} {'DUR':<7} {'MOVE':<8} {'MIN_D':<7} {'MAX_I'}")
print("-" * 85)

for filename in sorted(os.listdir(TEST_PATH)):
    if not filename.endswith(".json"): continue
    
    try:
        with open(os.path.join(TEST_PATH, filename)) as f:
            event = json.load(f)
        
        label     = event.get("label", "?")
        duration  = event["end_time"] - event["start_time"]
        num_scans = event["num_scans"]
        bg        = event.get("background_dist", 0.3)
        
        # 1. Calculate Movement (Standard Deviation of the middle 60%)
        mid_start = num_scans // 5
        mid_end   = num_scans - num_scans // 5
        mid_scans = event["distance_series"][mid_start:mid_end]
        mid_mins  = [min(s) for s in mid_scans] if mid_scans else [0]
        movement  = statistics.stdev(mid_mins) if len(mid_mins) > 1 else 0

        # 2. Calculate Global Min/Max and Intrusion
        # Flatten all scans into one single list of distances
        all_distances = [d for scan in event["distance_series"] for d in scan]
        
        if all_distances:
            abs_min = min(all_distances)
            max_intrusion = bg - abs_min
        else:
            abs_min = 0
            max_intrusion = 0

        # Print all stats in a single row
        print(f"{filename:<40} {label:<8} {duration:0.2f}s  {movement:.4f}  {abs_min:.3f}m  {max_intrusion:.4f}m")

    except Exception as e:
        print(f"Error processing {filename}: {e}")