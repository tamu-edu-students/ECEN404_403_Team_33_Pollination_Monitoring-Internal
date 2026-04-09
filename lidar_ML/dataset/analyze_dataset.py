# analyze_dataset.py
# Run this from your lidar_ML directory: python analyze_dataset.py
# It will tell you exactly what's wrong with your dataset and what to collect more of.

import os
import json
import statistics
import math
from collections import defaultdict

DATASET_PATH = "new_labeled_dataset"

def extract_key_features(event):
    background = event.get("background_dist", None)
    if background is None:
        all_d = [d for scan in event["distance_series"] for d in scan]
        background = max(all_d)

    duration     = event["end_time"] - event["start_time"]
    num_scans    = event["num_scans"]
    all_distances = [d for scan in event["distance_series"] for d in scan]

    min_dist     = min(all_distances)
    mean_dist    = statistics.mean(all_distances)
    max_intrusion  = background - min_dist
    mean_intrusion = statistics.mean([background - d for d in all_distances])
    intrusion_ratio = max_intrusion / background if background > 0 else 0

    scan_means = [statistics.mean(scan) for scan in event["distance_series"]]
    temporal_variation = statistics.stdev(scan_means) if len(scan_means) > 1 else 0

    # intrusion consistency: fraction of scans with >15% background blockage
    threshold = 0.15 * background
    sig_scans = sum(1 for scan in event["distance_series"] if (background - min(scan)) > threshold)
    intrusion_consistency = sig_scans / num_scans if num_scans > 0 else 0

    return {
        "duration": duration,
        "num_scans": num_scans,
        "background": background,
        "mean_distance": mean_dist,
        "max_intrusion": max_intrusion,
        "mean_intrusion": mean_intrusion,
        "intrusion_ratio": intrusion_ratio,
        "temporal_variation": temporal_variation,
        "intrusion_consistency": intrusion_consistency,
    }

def load_all():
    bee, notbee = [], []
    errors = []

    for filename in sorted(os.listdir(DATASET_PATH)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(DATASET_PATH, filename)
        try:
            with open(path) as f:
                event = json.load(f)
        except Exception as e:
            errors.append((filename, str(e)))
            continue

        label = event.get("label")
        if label is None:
            continue

        feats = extract_key_features(event)
        feats["filename"] = filename
        feats["flower_id"] = event.get("flower_id", "?")

        if label == "bee":
            bee.append(feats)
        else:
            notbee.append(feats)

    return bee, notbee, errors

def stats(values, label):
    if not values:
        return f"  {label}: NO DATA"
    return (f"  {label}: "
            f"min={min(values):.4f}  "
            f"max={max(values):.4f}  "
            f"mean={statistics.mean(values):.4f}  "
            f"stdev={statistics.stdev(values) if len(values)>1 else 0:.4f}")

def overlap_pct(bee_vals, notbee_vals):
    """What % of not_bee values fall inside the bee range (and vice versa)?"""
    if not bee_vals or not notbee_vals:
        return 0, 0
    bee_min, bee_max = min(bee_vals), max(bee_vals)
    notbee_min, notbee_max = min(notbee_vals), max(notbee_vals)

    # notbee values inside bee range
    nb_in_bee = sum(1 for v in notbee_vals if bee_min <= v <= bee_max)
    # bee values inside notbee range
    b_in_nb   = sum(1 for v in bee_vals   if notbee_min <= v <= notbee_max)

    return nb_in_bee / len(notbee_vals) * 100, b_in_nb / len(bee_vals) * 100

def main():
    bee, notbee, errors = load_all()

    print("=" * 65)
    print("DATASET QUALITY REPORT")
    print("=" * 65)
    print(f"  Bee samples:     {len(bee)}")
    print(f"  Not-bee samples: {len(notbee)}")
    print(f"  Load errors:     {len(errors)}")
    if errors:
        for f, e in errors:
            print(f"    {f}: {e}")

    features = [
        "duration", "num_scans", "max_intrusion", "mean_intrusion",
        "intrusion_ratio", "intrusion_consistency", "temporal_variation",
        "mean_distance", "background",
    ]

    print("\n" + "=" * 65)
    print("FEATURE OVERLAP ANALYSIS")
    print("(High overlap = model can't separate classes on this feature)")
    print("=" * 65)

    overlap_scores = {}
    for feat in features:
        b_vals  = [s[feat] for s in bee]
        nb_vals = [s[feat] for s in notbee]
        nb_in_b, b_in_nb = overlap_pct(b_vals, nb_vals)
        overlap_scores[feat] = (nb_in_b + b_in_nb) / 2

        sep = "✅ GOOD" if overlap_scores[feat] < 30 else ("⚠️  PARTIAL" if overlap_scores[feat] < 70 else "❌ BAD OVERLAP")
        print(f"\n{feat.upper()}  [{sep}]  avg_overlap={overlap_scores[feat]:.1f}%")
        print(stats(b_vals,  "bee   "))
        print(stats(nb_vals, "notbee"))

    print("\n" + "=" * 65)
    print("SUMMARY: WORST OVERLAPPING FEATURES")
    print("=" * 65)
    for feat, score in sorted(overlap_scores.items(), key=lambda x: -x[1]):
        bar = "█" * int(score / 5)
        print(f"  {feat:<25} {score:5.1f}%  {bar}")

    # -------------------------------------------------------
    # DUPLICATE / NEAR-DUPLICATE DETECTION
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("NEAR-DUPLICATE DETECTION (same class, suspiciously similar)")
    print("(These inflate your accuracy without adding real diversity)")
    print("=" * 65)

    def find_dupes(samples, class_name):
        dupes = []
        for i in range(len(samples)):
            for j in range(i+1, len(samples)):
                a, b = samples[i], samples[j]
                # similar if duration and num_scans are within 5%
                dur_sim  = abs(a["duration"]  - b["duration"])  / max(a["duration"],  0.001) < 0.05
                scan_sim = abs(a["num_scans"] - b["num_scans"]) / max(a["num_scans"], 1)     < 0.05
                dist_sim = abs(a["mean_distance"] - b["mean_distance"]) < 0.005
                if dur_sim and scan_sim and dist_sim:
                    dupes.append((a["filename"], b["filename"],
                                  a["duration"], a["num_scans"]))
        return dupes

    for class_name, samples in [("bee", bee), ("not_bee", notbee)]:
        dupes = find_dupes(samples, class_name)
        if dupes:
            print(f"\n  [{class_name}] {len(dupes)} near-duplicate pair(s):")
            for a, b, dur, ns in dupes[:10]:  # show max 10
                print(f"    {a}  ≈  {b}  (dur={dur:.2f}s, scans={ns})")
        else:
            print(f"\n  [{class_name}] No near-duplicates found ✅")

    # -------------------------------------------------------
    # DIVERSITY REPORT
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("DIVERSITY REPORT")
    print("(You want wide spread in these values, especially for not_bee)")
    print("=" * 65)

    for class_name, samples in [("bee", bee), ("not_bee", notbee)]:
        durations = [s["duration"] for s in samples]
        intrusions = [s["max_intrusion"] for s in samples]
        consistencies = [s["intrusion_consistency"] for s in samples]

        print(f"\n  [{class_name}]")
        print(f"    duration range:             {min(durations):.2f}s → {max(durations):.2f}s")
        print(f"    max_intrusion range:        {min(intrusions):.4f}m → {max(intrusions):.4f}m")
        print(f"    intrusion_consistency range:{min(consistencies):.2f} → {max(consistencies):.2f}")

        # bucket durations
        buckets = {"<1s": 0, "1-3s": 0, "3-8s": 0, ">8s": 0}
        for d in durations:
            if d < 1:    buckets["<1s"] += 1
            elif d < 3:  buckets["1-3s"] += 1
            elif d < 8:  buckets["3-8s"] += 1
            else:        buckets[">8s"] += 1
        print(f"    duration buckets: {buckets}")

    # -------------------------------------------------------
    # ACTIONABLE RECOMMENDATIONS
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("WHAT TO COLLECT MORE OF")
    print("=" * 65)

    bee_durations    = [s["duration"] for s in bee]
    notbee_durations = [s["duration"] for s in notbee]
    bee_intrusions   = [s["max_intrusion"] for s in bee]
    notbee_intrusions = [s["max_intrusion"] for s in notbee]
    notbee_consistency = [s["intrusion_consistency"] for s in notbee]

    if max(notbee_durations) < 10:
        print("  ⚠️  not_bee: Need longer events (>10s). Beetles/grasshoppers that sit")
        print("      for a long time are your hardest false-positive case.")

    if min(notbee_durations) > 1.0:
        print("  ⚠️  not_bee: Need very short events (<1s). Quick touches that barely")
        print("      trigger the detector but aren't pollinators.")

    if max(notbee_intrusions) < 0.03:
        print("  ⚠️  not_bee: All intrusions are shallow. Try placing the rubber model")
        print("      closer to the LiDAR to get deeper intrusion — tests if model")
        print("      can still reject based on behavior, not just depth.")

    if statistics.mean(notbee_consistency) > 0.5:
        print("  ⚠️  not_bee: intrusion_consistency is too high — not_bee events look")
        print("      like bees in terms of sustained contact. Add events where the")
        print("      object moves in and out inconsistently.")

    if len(bee) < 100:
        print(f"  ⚠️  bee: Only {len(bee)} samples. Aim for 100+ with varied durations")
        print("      and distances.")

    if len(notbee) < 80:
        print(f"  ⚠️  not_bee: Only {len(notbee)} samples. Aim for 80+ with varied")
        print("      durations, depths, and approach styles.")

    nb_in_b, _ = overlap_pct(
        [s["duration"] for s in bee],
        [s["duration"] for s in notbee]
    )
    if nb_in_b > 50:
        print("  ❌  CRITICAL: duration ranges heavily overlap. This is why the model")
        print("      struggles. You need not_bee events both much shorter AND much")
        print("      longer than your typical bee visit duration.")

    print()

if __name__ == "__main__":
    main()