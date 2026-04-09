# deduplicate_dataset.py
import os, json, shutil, statistics

DATASET_PATH = "new_labeled_dataset"
DEDUPED_PATH = "deduped_dataset"
os.makedirs(DEDUPED_PATH, exist_ok=True)

files = [f for f in os.listdir(DATASET_PATH) if f.endswith(".json")]
kept = []

for filename in sorted(files):
    with open(os.path.join(DATASET_PATH, filename)) as f:
        event = json.load(f)
    if event.get("label") is None:
        continue

    duration  = event["end_time"] - event["start_time"]
    num_scans = event["num_scans"]
    all_d     = [d for scan in event["distance_series"] for d in scan]
    mean_dist = statistics.mean(all_d)

    is_dupe = False
    for k in kept:
        if (abs(k["duration"]  - duration)  / max(duration, 0.001)  < 0.05 and
            abs(k["num_scans"] - num_scans)  / max(num_scans, 1)    < 0.05 and
            abs(k["mean_dist"] - mean_dist)                         < 0.005 and
            k["label"] == event["label"]):
            is_dupe = True
            break

    if not is_dupe:
        kept.append({"duration": duration, "num_scans": num_scans,
                     "mean_dist": mean_dist, "label": event["label"]})
        shutil.copy(os.path.join(DATASET_PATH, filename),
                    os.path.join(DEDUPED_PATH, filename))

bee_count    = sum(1 for k in kept if k["label"] == "bee")
notbee_count = sum(1 for k in kept if k["label"] != "bee")
print(f"Kept {len(kept)} unique events ({bee_count} bee, {notbee_count} not_bee)")
print(f"Removed {len(files) - len(kept)} near-duplicates")
print(f"Saved to: {DEDUPED_PATH}/")