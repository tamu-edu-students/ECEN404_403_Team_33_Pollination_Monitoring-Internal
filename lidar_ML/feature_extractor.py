# feature_extractor.py
import os
import json
import csv
import statistics

# Folder containing manually labeled event JSON files
LABELED_FOLDER = "new_labeled_dataset"

# Folder where the extracted features CSV will be stored
FEATURE_FOLDER = "features"

# Output CSV file
OUTPUT_FILE = os.path.join(FEATURE_FOLDER, "features.csv")

# Create features folder if it does not exist
os.makedirs(FEATURE_FOLDER, exist_ok=True)


def extract_features(event):
    """
    Extract numerical ML features from a single event JSON.
    These features describe how the object behaved in the LiDAR scans.
    """

    # -----------------------------
    # Basic timing features
    # -----------------------------
    duration = event["end_time"] - event["start_time"]
    num_scans = event["num_scans"]

    # scans per second during the event
    scans_per_second = num_scans / duration if duration > 0 else 0

    # background distance recorded when the flower was calibrated
    # background = event["background_dist"]
    background = event.get("background_dist", None)

    if background is None:
        # fallback: estimate from distances
        all_distances = [d for scan in event["distance_series"] for d in scan]
        background = max(all_distances)  # safe approximation

    # -----------------------------
    # Flatten all distances
    # Convert list of scans -> single list
    # -----------------------------
    all_distances = [d for scan in event["distance_series"] for d in scan]

    # -----------------------------
    # Basic distance statistics
    # -----------------------------
    min_distance = min(all_distances)
    max_distance = max(all_distances)
    mean_distance = statistics.mean(all_distances)

    std_distance = (
        statistics.stdev(all_distances)
        if len(all_distances) > 1 else 0
    )

    # -----------------------------
    # Intrusion calculations
    # How much the object blocked the background
    # -----------------------------
    intrusions = [background - d for d in all_distances]

    max_intrusion = max(intrusions)
    mean_intrusion = statistics.mean(intrusions)

    intrusion_std = (
        statistics.stdev(intrusions)
        if len(intrusions) > 1 else 0
    )

    # -----------------------------
    # NEW FEATURE 1
    # intrusion_ratio
    # Normalizes intrusion relative to background distance
    # Helps when flowers have different distances later
    # -----------------------------
    intrusion_ratio = max_intrusion / background if background > 0 else 0

    # -----------------------------
    # NEW FEATURE 2
    # temporal_variation
    # Measures movement of the object across time
    # Compute mean distance per scan, then measure variation
    # -----------------------------
    scan_means = [statistics.mean(scan) for scan in event["distance_series"]]

    temporal_variation = (
        statistics.stdev(scan_means)
        if len(scan_means) > 1 else 0
    )

    # Return all features as a list for CSV writing
    return [
    event.get("event_id", "unknown"),
    duration,
    num_scans,
    scans_per_second,
    min_distance,
    max_distance,
    mean_distance,
    std_distance,
    max_intrusion,
    mean_intrusion,
    intrusion_std,
    intrusion_ratio,
    temporal_variation,
    event.get("label", None)   # ✅ safe
]


def main():
    """
    Loop through labeled JSON events and extract features
    into a single CSV dataset for ML training.
    """

    # Only process JSON files
    files = sorted(f for f in os.listdir(LABELED_FOLDER) if f.endswith(".json"))

    with open(OUTPUT_FILE, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)

        # CSV header
        writer.writerow([
            "event_id",
            "duration",
            "num_scans",
            "scans_per_second",
            "min_distance",
            "max_distance",
            "mean_distance",
            "std_distance",
            "max_intrusion",
            "mean_intrusion",
            "intrusion_std",
            "intrusion_ratio",
            "temporal_variation",
            "label"
        ])

        # Process each labeled event
        for filename in files:
            path = os.path.join(LABELED_FOLDER, filename)

            try:
                # Load event JSON
                with open(path, "r", encoding="utf-8") as f:
                    event = json.load(f)
            except Exception as e:
                print(f"Skipping {filename}: {e}")
                continue

            # Extract features
            features = extract_features(event)

            # Write to CSV
            writer.writerow(features)

    print("Feature extraction complete.")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()