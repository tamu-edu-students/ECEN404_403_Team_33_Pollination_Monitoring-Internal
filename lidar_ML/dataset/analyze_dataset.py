# analyze_dataset.py
# Run this from your lidar_ML directory: python analyze_dataset.py

import os
import json
import statistics
import matplotlib.pyplot as plt
from collections import defaultdict

DATASET_PATH = "deduped_dataset" # "new_labeled_dataset"

# ============================================================
# SESSION TARGETS — update these if your targets change
# ============================================================
SESSION_TARGETS = {
    "A": ("bee",     1.0,  4.0, "fast drop + vibrate, 1-4s"),
    "B": ("bee",     4.0,  8.0, "fast drop + vibrate, 4-8s"),
    "C": ("not_bee", 2.0,  6.0, "still hold SHORT, 2-6s"),
    "D": ("not_bee", 8.0, 15.0, "still hold, 8-15s"),
    "E": ("not_bee",15.0, 25.0, "still hold, 15-25s"),
}
SESSION_TARGET_COUNTS = {"A": 60, "B": 40, "C": 50, "D": 40, "E": 20}


# ============================================================
# FEATURE EXTRACTION
# ============================================================
def extract_key_features(event):
    background = event.get("background_dist", None)
    if background is None:
        all_d = [d for scan in event["distance_series"] for d in scan]
        background = max(all_d)

    duration      = event["end_time"] - event["start_time"]
    num_scans     = event["num_scans"]
    all_distances = [d for scan in event["distance_series"] for d in scan]

    min_dist        = min(all_distances)
    mean_dist       = statistics.mean(all_distances)
    max_intrusion   = background - min_dist
    mean_intrusion  = statistics.mean([background - d for d in all_distances])
    intrusion_ratio = max_intrusion / background if background > 0 else 0

    scan_means = [statistics.mean(scan) for scan in event["distance_series"]]
    temporal_variation = statistics.stdev(scan_means) if len(scan_means) > 1 else 0

    threshold = 0.15 * background
    sig_scans = sum(1 for scan in event["distance_series"] if (background - min(scan)) > threshold)
    intrusion_consistency = sig_scans / num_scans if num_scans > 0 else 0

    mid_start = num_scans // 5
    mid_end   = num_scans - num_scans // 5
    mid_scans = event["distance_series"][mid_start:mid_end]
    mid_min_distances = [min(scan) for scan in mid_scans] if mid_scans else [0]
    movement_during_visit = (
        statistics.stdev(mid_min_distances) if len(mid_min_distances) > 1 else 0
    )

    scan_max_intrusions = [background - min(scan) for scan in event["distance_series"]]
    peak_idx = scan_max_intrusions.index(max(scan_max_intrusions))
    peak_intrusion_timing = peak_idx / num_scans if num_scans > 0 else 0.5

    return {
        "duration":               duration,
        "num_scans":              num_scans,
        "background":             background,
        "mean_distance":          mean_dist,
        "max_intrusion":          max_intrusion,
        "mean_intrusion":         mean_intrusion,
        "intrusion_ratio":        intrusion_ratio,
        "temporal_variation":     temporal_variation,
        "intrusion_consistency":  intrusion_consistency,
        "movement_during_visit":  movement_during_visit,
        "peak_intrusion_timing":  peak_intrusion_timing,
    }


# ============================================================
# LOAD ALL
# ============================================================
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
        feats["filename"]  = filename
        feats["flower_id"] = event.get("flower_id", "?")

        if label == "bee":
            bee.append(feats)
        else:
            notbee.append(feats)

    return bee, notbee, errors


# ============================================================
# HELPERS
# ============================================================
def stats_line(values, label):
    if not values:
        return f"  {label}: NO DATA"
    return (f"  {label}: "
            f"min={min(values):.4f}  "
            f"max={max(values):.4f}  "
            f"mean={statistics.mean(values):.4f}  "
            f"stdev={statistics.stdev(values) if len(values) > 1 else 0:.4f}")

def overlap_pct(bee_vals, notbee_vals):
    if not bee_vals or not notbee_vals:
        return 0, 0
    bee_min,    bee_max    = min(bee_vals),    max(bee_vals)
    notbee_min, notbee_max = min(notbee_vals), max(notbee_vals)
    nb_in_bee = sum(1 for v in notbee_vals if bee_min    <= v <= bee_max)
    b_in_nb   = sum(1 for v in bee_vals   if notbee_min <= v <= notbee_max)
    return nb_in_bee / len(notbee_vals) * 100, b_in_nb / len(bee_vals) * 100

def assign_session(duration, label):
    for sess, (sess_label, dmin, dmax, _) in SESSION_TARGETS.items():
        if sess_label == label and dmin <= duration < dmax:
            return sess
    return "?"

# ============================================================
# SESSION VISUALIZATION (Improved)
# ============================================================
def plot_session_distribution(session_counts):
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    # 1. Data Preparation
    sessions = sorted(SESSION_TARGETS.keys())
    current = [session_counts[s] for s in sessions]
    targets = [SESSION_TARGET_COUNTS[s] for s in sessions]
    
    labels  = [SESSION_TARGETS[s][0].upper() for s in sessions]
    behaviors = [SESSION_TARGETS[s][3].replace(", ", "\n") for s in sessions]

    # 2. Colors & Aesthetics
    COLOR_BEE = "#FFC107"      # Golden Amber
    COLOR_NOTBEE = "#009688"   # Modern Teal
    COLOR_GOAL = "#ECEFF1"     # Soft Grey for the 'track'
    
    colors = [COLOR_BEE if SESSION_TARGETS[s][0] == "bee" else COLOR_NOTBEE for s in sessions]
    
    x = np.arange(len(sessions))
    width = 0.6 

    # 3. Create the Plot
    fig, ax = plt.subplots(figsize=(11, 6.5)) # Slightly taller to accommodate padding
    ax.set_facecolor("white")
    
    # Draw Background Bars (Target Goal)
    ax.bar(x, targets, width, color=COLOR_GOAL, edgecolor="#CFD8DC", 
           linewidth=1, label="Target Goal", zorder=2)
    
    # Draw Foreground Bars (Actual Progress)
    actual_bars = ax.bar(x, current, width * 0.8, color=colors, edgecolor="black", 
                         alpha=0.9, linewidth=1.2, label="Current Progress", zorder=3)

    # 4. Add Text Annotations
    for i, bar in enumerate(actual_bars):
        have = current[i]
        need = targets[i]
        pct = (have / need * 100) if need > 0 else 0
        
        # Current count on top
        ax.text(bar.get_x() + bar.get_width()/2, have + 0.5, 
                f"{have}", ha='center', va='bottom', fontweight='bold', fontsize=11, zorder=4)
        
        # Percentage text moved slightly higher (-0.8 instead of -1.8)
        ax.text(bar.get_x() + bar.get_width()/2, -0.8, 
                f"{pct:.0f}%", ha='center', va='top', fontsize=10, 
                fontweight='bold', color="#455A64")

    # 5. Axes & Labels (Full Behavior Strings)
    ax.set_xticks(x)
    # Multi-line labels: Session ID -> Class -> Behavior
    # We now use 'full_behaviors' which includes the timing like "1-4s"
    xtick_labels = [f"Session {s}\n{l}\n({b})" for s, l, b in zip(sessions, labels, behaviors)]
    ax.set_xticklabels(xtick_labels, fontsize=9.5, fontweight='medium')
    
    # CRITICAL: Increase pad to push the session labels down, away from the % text
    ax.tick_params(axis='x', which='major', pad=15) 
    
    ax.set_title("Lidar Dataset: Session Collection Progress", fontsize=16, fontweight='bold', pad=25)
    ax.set_ylabel("Number of Samples / Events", fontsize=12, labelpad=10)
    
    # 6. Styling
    ax.yaxis.grid(True, linestyle='--', which='major', color='grey', alpha=0.2, zorder=0)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#90A4AE')
    ax.spines['bottom'].set_color('#90A4AE')

    # 7. Legend
    legend_elements = [
        Patch(facecolor=COLOR_BEE, edgecolor='black', label='Bee Samples'),
        Patch(facecolor=COLOR_NOTBEE, edgecolor='black', label='Not-Bee Samples'),
        Patch(facecolor=COLOR_GOAL, edgecolor='#CFD8DC', label='Collection Goal')
    ]
    ax.legend(handles=legend_elements, loc='upper right', frameon=False, fontsize=10)

    plt.tight_layout()
    plt.savefig("dataset_report.png")
    plt.show()

# ============================================================
# MAIN
# ============================================================
def main():
    bee, notbee, errors = load_all()
    all_samples = [("bee", s) for s in bee] + [("not_bee", s) for s in notbee]

    print("=" * 65)
    print("DATASET QUALITY REPORT")
    print("=" * 65)
    print(f"  Bee samples:     {len(bee)}")
    print(f"  Not-bee samples: {len(notbee)}")
    print(f"  Load errors:     {len(errors)}")
    if errors:
        for f, e in errors:
            print(f"    {f}: {e}")

    # -------------------------------------------------------
    # SESSION COVERAGE
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("SESSION COVERAGE")
    print("(How many samples do you have per collection session?)")
    print("=" * 65)

    session_counts           = defaultdict(int)
    session_unmatched_bee    = []
    session_unmatched_notbee = []

    for label, s in all_samples:
        sess = assign_session(s["duration"], label)
        if sess != "?":
            session_counts[sess] += 1
        else:
            if label == "bee":
                session_unmatched_bee.append(s["duration"])
            else:
                session_unmatched_notbee.append(s["duration"])

    print(f"\n  {'Sess':<6} {'Label':<10} {'Behavior':<35} {'Have':>5} {'Need':>5}  Status")
    print(f"  {'-'*4:<6} {'-'*8:<10} {'-'*33:<35} {'-'*4:>5} {'-'*4:>5}  {'-'*15}")
    for sess in sorted(SESSION_TARGETS):
        label, dmin, dmax, behavior = SESSION_TARGETS[sess]
        have   = session_counts[sess]
        target = SESSION_TARGET_COUNTS[sess]
        status = "✅ done" if have >= target else f"⚠️  need {target - have} more"
        print(f"  {sess:<6} {label:<10} {behavior:<35} {have:>5} {target:>5}  {status}")

    if session_unmatched_bee:
        print(f"\n  [bee] {len(session_unmatched_bee)} samples outside session ranges: "
              f"{[f'{d:.1f}s' for d in sorted(session_unmatched_bee)]}")
    if session_unmatched_notbee:
        print(f"\n  [not_bee] {len(session_unmatched_notbee)} samples outside session ranges: "
              f"{[f'{d:.1f}s' for d in sorted(session_unmatched_notbee)]}")

    # -------------------------------------------------------
    # FEATURE OVERLAP ANALYSIS
    # -------------------------------------------------------
    all_features = [
        "duration", "num_scans", "max_intrusion", "mean_intrusion",
        "intrusion_ratio", "intrusion_consistency", "temporal_variation",
        "movement_during_visit", "peak_intrusion_timing",
        "mean_distance", "background",
    ]

    print("\n" + "=" * 65)
    print("FEATURE OVERLAP ANALYSIS")
    print("(High overlap = model can't separate classes on this feature)")
    print("=" * 65)

    overlap_scores = {}
    for feat in all_features:
        b_vals  = [s[feat] for s in bee]
        nb_vals = [s[feat] for s in notbee]
        nb_in_b, b_in_nb = overlap_pct(b_vals, nb_vals)
        overlap_scores[feat] = (nb_in_b + b_in_nb) / 2

        sep = ("✅ GOOD"     if overlap_scores[feat] < 30  else
               "⚠️  PARTIAL" if overlap_scores[feat] < 70  else
               "❌ BAD")
        print(f"\n{feat.upper()}  [{sep}]  avg_overlap={overlap_scores[feat]:.1f}%")
        print(stats_line(b_vals,  "bee   "))
        print(stats_line(nb_vals, "notbee"))

    print("\n" + "=" * 65)
    print("SUMMARY: WORST → BEST OVERLAPPING FEATURES")
    print("=" * 65)
    for feat, score in sorted(overlap_scores.items(), key=lambda x: -x[1]):
        bar    = "█" * int(score / 5)
        status = "✅" if score < 30 else ("⚠️ " if score < 70 else "❌")
        print(f"  {status} {feat:<25} {score:5.1f}%  {bar}")

    # -------------------------------------------------------
    # NEW FEATURE SEPARATION CHECK
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("NEW FEATURE SEPARATION CHECK")
    print("(Are the new behavioral features doing their job?)")
    print("=" * 65)

    b_mov  = [s["movement_during_visit"] for s in bee]
    nb_mov = [s["movement_during_visit"] for s in notbee]
    if b_mov and nb_mov:
        diff = statistics.mean(b_mov) - statistics.mean(nb_mov)
        print(f"\n  movement_during_visit")
        print(f"    bee mean:    {statistics.mean(b_mov):.5f}")
        print(f"    notbee mean: {statistics.mean(nb_mov):.5f}")
        if diff > 0.001:
            print(f"    ✅ Bees ARE more active (+{diff:.5f}) — vibration working")
        elif diff > 0:
            print(f"    ⚠️  Tiny difference (+{diff:.5f}) — vibrate MORE during bee sessions")
        else:
            print(f"    ❌ Bees LESS active than not_bees — vibration not working")
            print(f"       Re-collect sessions A and B with deliberate finger trembling")

    b_pit  = [s["peak_intrusion_timing"] for s in bee]
    nb_pit = [s["peak_intrusion_timing"] for s in notbee]
    if b_pit and nb_pit:
        diff = statistics.mean(nb_pit) - statistics.mean(b_pit)
        print(f"\n  peak_intrusion_timing  (0.0=early peak, 1.0=late peak)")
        print(f"    bee mean:    {statistics.mean(b_pit):.3f}")
        print(f"    notbee mean: {statistics.mean(nb_pit):.3f}")
        if diff > 0.05:
            print(f"    ✅ Bees peak earlier as expected (+{diff:.3f} difference)")
        else:
            print(f"    ⚠️  No clear early/late difference ({diff:.3f}) — feature may be weak")

    b_ic  = [s["intrusion_consistency"] for s in bee]
    nb_ic = [s["intrusion_consistency"] for s in notbee]
    if b_ic and nb_ic:
        diff = statistics.mean(nb_ic) - statistics.mean(b_ic)
        print(f"\n  intrusion_consistency")
        print(f"    bee mean:    {statistics.mean(b_ic):.3f}")
        print(f"    notbee mean: {statistics.mean(nb_ic):.3f}")
        if diff > 0.05:
            print(f"    ✅ not_bee has higher consistency (+{diff:.3f}) — still-hold working")
        elif diff > 0:
            print(f"    ⚠️  Small difference ({diff:.3f}) — collect more still-hold sessions C/D/E")
        else:
            print(f"    ❌ bee has higher consistency than not_bee — check Session E data")

    # -------------------------------------------------------
    # NEAR-DUPLICATE DETECTION
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("NEAR-DUPLICATE DETECTION")
    print("(These inflate accuracy without adding real diversity)")
    print("=" * 65)

    def find_dupes(samples):
        dupes = []
        for i in range(len(samples)):
            for j in range(i + 1, len(samples)):
                a, b = samples[i], samples[j]
                dur_sim  = abs(a["duration"]     - b["duration"])     / max(a["duration"],     0.001) < 0.05
                scan_sim = abs(a["num_scans"]     - b["num_scans"])    / max(a["num_scans"],    1)     < 0.05
                dist_sim = abs(a["mean_distance"] - b["mean_distance"])                                < 0.005
                if dur_sim and scan_sim and dist_sim:
                    dupes.append((a["filename"], b["filename"], a["duration"], a["num_scans"]))
        return dupes

    for class_name, samples in [("bee", bee), ("not_bee", notbee)]:
        dupes = find_dupes(samples)
        if dupes:
            print(f"\n  [{class_name}] {len(dupes)} near-duplicate pair(s):")
            for a, b, dur, ns in dupes[:10]:
                print(f"    {a}  ≈  {b}  (dur={dur:.2f}s, scans={ns})")
            if len(dupes) > 10:
                print(f"    ... and {len(dupes) - 10} more")
        else:
            print(f"\n  [{class_name}] No near-duplicates found ✅")

    # -------------------------------------------------------
    # DIVERSITY REPORT
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("DIVERSITY REPORT")
    print("=" * 65)

    for class_name, samples in [("bee", bee), ("not_bee", notbee)]:
        durations     = [s["duration"]             for s in samples]
        intrusions    = [s["max_intrusion"]         for s in samples]
        consistencies = [s["intrusion_consistency"] for s in samples]
        movements     = [s["movement_during_visit"] for s in samples]

        buckets = {"<1s": 0, "1-3s": 0, "3-8s": 0, "8-15s": 0, ">15s": 0}
        for d in durations:
            if   d < 1:   buckets["<1s"]   += 1
            elif d < 3:   buckets["1-3s"]  += 1
            elif d < 8:   buckets["3-8s"]  += 1
            elif d < 15:  buckets["8-15s"] += 1
            else:         buckets[">15s"]  += 1

        print(f"\n  [{class_name}]")
        print(f"    duration range:              {min(durations):.2f}s → {max(durations):.2f}s")
        print(f"    max_intrusion range:         {min(intrusions):.4f}m → {max(intrusions):.4f}m")
        print(f"    intrusion_consistency range: {min(consistencies):.3f} → {max(consistencies):.3f}")
        print(f"    movement_during_visit range: {min(movements):.5f} → {max(movements):.5f}")
        print(f"    duration buckets:            {buckets}")

    # -------------------------------------------------------
    # ACTIONABLE RECOMMENDATIONS
    # -------------------------------------------------------
    print("\n" + "=" * 65)
    print("WHAT TO COLLECT MORE OF")
    print("=" * 65)

    any_rec = False

    for sess in sorted(SESSION_TARGETS):
        label, dmin, dmax, behavior = SESSION_TARGETS[sess]
        have   = session_counts[sess]
        target = SESSION_TARGET_COUNTS[sess]
        if have < target:
            print(f"  ⚠️  Session {sess} [{label}] ({behavior}): have {have}, need {target - have} more")
            any_rec = True

    notbee_durations   = [s["duration"]             for s in notbee]
    notbee_consistency = [s["intrusion_consistency"] for s in notbee]
    b_mov_mean  = statistics.mean([s["movement_during_visit"] for s in bee])    if bee    else 0
    nb_mov_mean = statistics.mean([s["movement_during_visit"] for s in notbee]) if notbee else 0

    if notbee_durations and min(notbee_durations) > 1.0:
        print("  ⚠️  not_bee: No events under 1s — very short touches won't be caught by pre-filter")
        any_rec = True

    if notbee_consistency and statistics.mean(notbee_consistency) > 0.7:
        print("  ⚠️  not_bee: intrusion_consistency high — ensure zero movement during not_bee sessions")
        any_rec = True

    if b_mov_mean <= nb_mov_mean:
        print("  ❌  movement_during_visit not separating — re-collect bee sessions A+B with vibration")
        any_rec = True

    if not any_rec:
        print("  ✅ Dataset looks good! Run train_model.py and check cross-val F1.")
    
    # -------------------------------------------------------
    # SESSION PLOT
    # -------------------------------------------------------
    plot_session_distribution(session_counts)

    print()


if __name__ == "__main__":
    main()