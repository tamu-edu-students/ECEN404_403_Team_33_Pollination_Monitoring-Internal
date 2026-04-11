import os
import json

RAW_FOLDER = "dataset/raw_dataset"
LABELED_FOLDER = "dataset/test_dataset"

os.makedirs(LABELED_FOLDER, exist_ok=True)

def compute_summary(event):
    duration = event["end_time"] - event["start_time"]

    # flatten distance_series
    all_distances = [d for scan in event["distance_series"] for d in scan]
    min_dist = min(all_distances)
    max_dist = max(all_distances)

    return duration, min_dist, max_dist


def main():
    # Filter for .json files and ignore hidden files like .DS_Store
    files = sorted([f for f in os.listdir(RAW_FOLDER) if f.endswith('.json')])

    if not files:
        print(f"No JSON files found in {RAW_FOLDER}")
        return

    for filename in files:
        raw_path = os.path.join(RAW_FOLDER, filename)
        labeled_path = os.path.join(LABELED_FOLDER, filename)

        # skip already labeleds
        if os.path.exists(labeled_path):
            continue

        try:
            # Added encoding="utf-8" to be safe
            with open(raw_path, "r", encoding="utf-8") as f:
                event = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Skipping {filename}: Not a valid JSON or corrupted encoding. Error: {e}")
            continue

        duration, min_dist, max_dist = compute_summary(event)

        print("\n==============================")
        print(f"Event ID: {event['event_id']}")
        print(f"Scans: {event['num_scans']}")
        print(f"Duration: {duration:.3f} sec")
        print(f"Min distance: {min_dist:.3f} m")
        print(f"Max distance: {max_dist:.3f} m")
        print("==============================")

        label = input("Label this event (bee / not_bee / skip): ").strip()

        if label not in ["bee", "not_bee"]:
            print("Skipping...")
            continue

        event["label"] = label

        with open(labeled_path, "w") as f:
            json.dump(event, f, indent=4)

        print(f"Saved to {LABELED_FOLDER}")

    print("\nLabeling complete.")


if __name__ == "__main__":
    main()