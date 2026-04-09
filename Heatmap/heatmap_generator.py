# heatmap_generator.py
import io
import json
import numpy as np
import math
import os
import json 
from datetime import datetime
import matplotlib.pyplot as plt
from lidar_ML.bee_classifier import BeeClassifier

ANGLE_START_DEG = 0.0
ANGLE_INCREMENT_DEG = 0.5

# ==========================================
# INITIALIZE CLASSIFIER WITH PATH
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)

MODEL_PATH = os.path.join(PARENT_DIR, 'lidar_ML', 'models', "bee_model3.pkl")

# Instantiate the classifier
classifier = BeeClassifier(MODEL_PATH)

# ==========================================
# GLOBAL STORAGE FOR ACCUMULATED VISITS
# ==========================================
flower_visit_counts = {}  # flower_id (str) -> {count, x, y}  OR  (x,y) tuple -> count
FLOWER_MATCH_THRESHOLD = 0.05  # meters

# ==========================================
# HELPERS
# ==========================================
def polar_to_xy(distance_m, angle_index):
    angle_deg = ANGLE_START_DEG + angle_index * ANGLE_INCREMENT_DEG
    angle_rad = math.radians(angle_deg)
    x = distance_m * math.cos(angle_rad)
    y = distance_m * math.sin(angle_rad)
    return x, y

def find_existing_flower(x, y):
    """
    Check if this detection is near an existing flower (fallback position-based matching).
    Only applies when flower_id is None.
    """
    for key in flower_visit_counts.keys():
        if isinstance(key, tuple):
            fx, fy = key
            dist = math.sqrt((x - fx) ** 2 + (y - fy) ** 2)
            if dist < FLOWER_MATCH_THRESHOLD:
                return key
    return None

def is_daytime():
    hour = datetime.now().hour
    return 6 <= hour < 18   # simple version

# ==========================================
# PROCESS FILE
# ==========================================
def process_file(filepath, camera_data=None, flower_id=None):
    new_positions = []
    if not os.path.exists(filepath):
        return new_positions

    print(f"\n========== EVENT PROCESSING FILE: {os.path.basename(filepath)} ==========")
    use_camera = is_daytime() and camera_data is not None

    if use_camera:
        print("[FUSION MODE] DAY → Confidence Fusion (Camera vs LiDAR)")
    else:
        print("[FUSION MODE] NIGHT → LiDAR Only")

    print(f"{'EVENT_ID':<15} {'FLOWER_ID':<15} {'SOURCE':<12} {'PREDICTION':<20} {'CONFIDENCE':<12} {'STATUS'}")
    print("-" * 90)
        
    with open(filepath, "r") as f:
        for line in f:
            if not line.strip(): 
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[ERROR] Skipping malformed JSON line: {e}")
                continue

            # Predict returns (label, lidar_conf)
            try:
                label, lidar_conf = classifier.predict(event)
            except Exception as e:
                print(f"[ERROR] Skipping event due to: {e}")
                continue
            
            event_id = event.get("event_id", "N/A")
            lidar_is_bee = (label == "bee")

            # ======================================
            # CAMERA DATA
            # ======================================
            camera_conf = 0.0
            camera_is_bee = False
            camera_is_non_pollinator = False
            camera_non_pollinator_conf = 0.0
            
            if camera_data:
                cam = camera_data[0]
                camera_conf = cam.get("confidence", 0.0)
                camera_is_bee = cam.get("pollinator", False)
                camera_is_non_pollinator = cam.get("non_pollinator", False)
                camera_non_pollinator_conf = cam.get("non_pollinator_confidence", 0.0)
                top_pollinator_class = cam.get("top_pollinator_class") or "pollinator"
                top_non_pollinator_class = cam.get("top_non_pollinator_class") or "non_pollinator"
            
            # ======================================
            # LOG BOTH SOURCES
            # ======================================
            print(f"{str(event_id):<15} {str(flower_id):<15} {'LIDAR':<12} "
                f"{'pollinator' if lidar_is_bee else 'not_pollinator':<20} "
                f"{lidar_conf:.3f}            -")

            if camera_data:
                if camera_is_non_pollinator and camera_non_pollinator_conf >= camera_conf:
                    cam_label = top_non_pollinator_class      # e.g. "beetle"
                    cam_log_conf = camera_non_pollinator_conf
                elif camera_is_bee:
                    cam_label = top_pollinator_class          # e.g. "butterfly"
                    cam_log_conf = camera_conf
                else:
                    cam_label = "no_detection"
                    cam_log_conf = 0.0

                print(f"{str(event_id):<15} {str(flower_id):<15} {'CAMERA':<12} "
                      f"{cam_label:<20} "
                      f"{cam_log_conf:.3f}            -")
                
            # ======================================
            # FUSION LOGIC
            # ======================================
            if use_camera:
                # Camera confidently sees a non-pollinator and beats LiDAR → veto
                if camera_is_non_pollinator and camera_non_pollinator_conf >= lidar_conf:
                    is_bee = False
                    source = "CAMERA"
                    final_conf = camera_non_pollinator_conf
                # Otherwise compare pollinator confidences as before
                elif camera_conf >= lidar_conf:
                    is_bee = camera_is_bee
                    source = "CAMERA"
                    final_conf = camera_conf
                else:
                    is_bee = lidar_is_bee
                    source = "LIDAR"
                    final_conf = lidar_conf
            else:
                is_bee = lidar_is_bee
                source = "LIDAR"
                final_conf = lidar_conf

            status = "DETECTED" if is_bee else "SKIPPED"

            print(f"{str(event_id):<15} {str(flower_id):<15} {source:<12} "
                  f"{'pollinator' if is_bee else 'not_pollinator':<20} "
                  f"{final_conf:.3f}            {status}")

            print("-" * 90)

            if not is_bee:
                continue

            # ======================================
            # POSITION COMPUTATION
            # ======================================
            angles = event.get("angles")
            distance_series = event.get("distance_series")
            if not angles or not distance_series:
                print("[WARNING] Missing angles or distance_series -- skipping event")
                continue

            avg_distances = np.mean(distance_series, axis=0)

            xs = []
            ys = []

            for angle_index, distance in zip(angles, avg_distances):
                x, y = polar_to_xy(distance, angle_index)
                xs.append(x)
                ys.append(y)

            if xs and ys:
                new_positions.append((np.mean(xs), np.mean(ys)))

    return new_positions

# ==========================================
# MAIN HEATMAP GENERATOR
# ==========================================
def generate_heatmap_png(filepath, camera_data=None, flower_id=None):

    new_positions = process_file(filepath, camera_data, flower_id)

    # ==========================================
    # UPDATE GLOBAL FLOWER COUNTS
    # ==========================================
    for x, y in new_positions:
        if flower_id is not None:
            # --- flower_id string key ---
            if flower_id in flower_visit_counts:
                flower_visit_counts[flower_id]["count"] += 1
            else:
                flower_visit_counts[flower_id] = {
                    "count": 1,
                    "x": x,
                    "y": y
                }
        else:
            # --- fallback: position-based (x,y) tuple key ---
            existing = find_existing_flower(x, y)
            if existing:
                flower_visit_counts[existing] += 1
            else:
                flower_visit_counts[(x, y)] = 1

    pollinator_detected = len(new_positions) > 0
    detection_json_bytes = json.dumps({"pollinator_detected": pollinator_detected}).encode("utf-8")

    if len(flower_visit_counts) == 0:
        print("[HEATMAP] No visits yet — generating empty heatmap.")

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_title("Pollinator Activity Map\nNo visits detected")
        ax.set_xlabel("Distance X (m)")
        ax.set_ylabel("Distance Y (m)")

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=300)
        plt.close(fig)

        buffer.seek(0)
        return buffer.read(), detection_json_bytes

    # if len(flower_visit_counts) == 0:
    #     print("[HEATMAP] No flowers tracked yet — skipping heatmap generation.")
    #     return None, detection_json_bytes
    
    # ==========================================
    # BUILD PLOT DATA — FIXED: single unified loop
    # ==========================================
    xs = []
    ys = []
    counts = []

    for key, data in flower_visit_counts.items():
        if isinstance(key, str):        # flower_id case
            xs.append(data["x"])
            ys.append(data["y"])
            counts.append(data["count"])
        else:                           # fallback (x, y) tuple case
            xs.append(key[0])
            ys.append(key[1])
            counts.append(data)

    total_visits = sum(counts)

    # ==========================================
    # PLOT
    # ==========================================
    fig, ax = plt.subplots(figsize=(8, 8))

    ax.set_facecolor("#f8fafc")
    fig.patch.set_facecolor("#ffffff")

    scatter = ax.scatter(
        xs,
        ys,
        s=[150 + c * 120 for c in counts],
        c=counts,
        cmap="viridis",
        alpha=0.85,
        edgecolors="white",
        linewidth=1.5
    )

    plt.colorbar(scatter, ax=ax, label="Visits per Flower")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlabel("Distance X (m)")
    ax.set_ylabel("Distance Y (m)")

    # Build heatmap summary
    flower_summary_parts = []

    for key, data in flower_visit_counts.items():
        if isinstance(key, str):
            flower_summary_parts.append(f"{key} ({data['count']})")
        else:
            flower_summary_parts.append(f"({key[0]:.2f},{key[1]:.2f}) ({data})")

    summary_line = " | ".join(flower_summary_parts)

    # Final title
    title_text = "Pollinator Activity Map"

    if summary_line:
        title_text += f"\nTotal Visits: {total_visits} {summary_line}"

    ax.set_title(title_text)

    # flower_summary_lines = []
    # for key, data in flower_visit_counts.items():
    #     if isinstance(key, str):
    #         flower_summary_lines.append(f"{key}: {data['count']}")
    #     else:
    #         flower_summary_lines.append(f"({key[0]:.2f}, {key[1]:.2f}): {data}")
 
    # title_text = f"Pollinator Activity Map\nTotal Visits: {total_visits}"
    # if flower_summary_lines:
    #     title_text += "\n\nVisits per Flower:\n" + "\n".join(flower_summary_lines)
 
    # ax.set_title(title_text)
    ax.set_aspect("equal", adjustable="box")

    padding = 0.2
    ax.set_xlim(min(xs) - padding, max(xs) + padding)
    ax.set_ylim(min(ys) - padding, max(ys) + padding)

    # ==========================================
    # SAVE PNG LOCALLY
    # ==========================================
    output_dir = "generated_heatmaps"

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    timestamp = datetime.now().strftime("%m-%d-%Y_%H.%M.%S.%f")[:-3]
    filename = f"heatmap_{timestamp}.png"
    file_path = os.path.join(output_dir, filename)

    fig.savefig(file_path, dpi=300)

    print(f"[HEATMAP] Saved locally: {file_path}")
    print(f"[HEATMAP] Total visits so far: {total_visits}")

    # Print per-flower breakdown
    print("[HEATMAP] Visits per flower:")
    for key, data in flower_visit_counts.items():
        if isinstance(key, str):
            print(f"  - {key:<10} → {data['count']} visits")
        else:
            print(f"  - ({key[0]:.2f}, {key[1]:.2f}) → {data} visits")

    # ==========================================
    # ALSO RETURN PNG BYTES FOR NETWORK
    # ==========================================
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=300)
    plt.close(fig)

    buffer.seek(0)
    return buffer.read(), detection_json_bytes
