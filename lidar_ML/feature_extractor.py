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
    scans_per_second = num_scans / duration if duration > 0 else 0 # scans per second during the event

    # -----------------------------
    # Background distance
    # This is the distance to the flower when no object is present
    # -----------------------------
    background = event.get("background_dist", None) # background distance recorded when the flower was calibrated
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

    # intrusion_ratio: normalizes intrusion relative to backgrounddistances later
    intrusion_ratio = max_intrusion / background if background > 0 else 0

    # -----------------------------
    # temporal_variation
    # Measures movement of the object across time
    # Compute mean distance per scan, then measure variation
    # -----------------------------
    scan_means = [statistics.mean(scan) for scan in event["distance_series"]]
    temporal_variation = (
        statistics.stdev(scan_means)
        if len(scan_means) > 1 else 0
    )

    # -----------------------------
    # intrusion_consistency
    # Fraction of scans with meaningful intrusion (> 15% of background).
    # Bees: sustained contact → high value.
    # Brief/shallow visits → low value.
    # -----------------------------
    intrusion_threshold = 0.15 * background
    significant_scans = sum(
        1 for scan in event["distance_series"]
        if (background - min(scan)) > intrusion_threshold
    )
    intrusion_consistency = significant_scans / num_scans if num_scans > 0 else 0

    # -----------------------------
    # movement_during_visit
    # Std dev of per-scan minimum distances during middle 60% of visit.
    # Bees vibrate/wiggle while feeding → high value.
    # Beetles sit completely still → low value.
    # This is the key feature for distinguishing vibrating bee simulation
    # from still beetle simulation with a fishing string.
    # -----------------------------
    mid_start = num_scans // 5
    mid_end   = num_scans - num_scans // 5
    mid_scans = event["distance_series"][mid_start:mid_end]
    mid_min_distances = [min(scan) for scan in mid_scans] if mid_scans else [0]
    movement_during_visit = (
        statistics.stdev(mid_min_distances) if len(mid_min_distances) > 1 else 0
    )

    # -----------------------------
    # peak_intrusion_timing
    # When in the event did maximum intrusion occur? (0=start, 1=end)
    # Bees dive in fast → peak early (low value).
    # Beetles crawl on slowly → peak later or flat (mid/high value).
    # -----------------------------
    scan_max_intrusions = [background - min(scan) for scan in event["distance_series"]]
    peak_idx = scan_max_intrusions.index(max(scan_max_intrusions))
    peak_intrusion_timing = peak_idx / num_scans if num_scans > 0 else 0.5

    # Return all features as a list for CSV writing
    return [
        event.get("event_id", "unknown"),   # index 0  — dropped in training
        duration,                            # index 1
        num_scans,                           # index 2
        scans_per_second,                    # index 3
        min_distance,                        # index 4
        max_distance,                        # index 5
        mean_distance,                       # index 6
        std_distance,                        # index 7
        max_intrusion,                       # index 8
        mean_intrusion,                      # index 9
        intrusion_std,                       # index 10
        intrusion_ratio,                     # index 11
        temporal_variation,                  # index 12
        intrusion_consistency,               # index 13
        movement_during_visit,               # index 14
        peak_intrusion_timing,               # index 15
        event.get("label", None)             # index 16 — dropped in training
    ]

def main():
    """
    Loop through labeled JSON events and extract features
    into a single CSV dataset for ML training.
    """

    # Create features folder if it does not exist
    os.makedirs(FEATURE_FOLDER, exist_ok=True)

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
            "intrusion_consistency",
            "movement_during_visit",
            "peak_intrusion_timing",
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