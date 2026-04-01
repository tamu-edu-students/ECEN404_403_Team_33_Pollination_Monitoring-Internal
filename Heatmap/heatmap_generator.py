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

MODEL_PATH = os.path.join(PARENT_DIR, 'lidar_ML', 'models', "bee_model.pkl")

# Instantiate the classifier
classifier = BeeClassifier(MODEL_PATH)

# ==========================================
# GLOBAL STORAGE FOR ACCUMULATED VISITS
# ==========================================
flower_visit_counts = {}
FLOWER_MATCH_THRESHOLD = 0.15  # meters

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
    Check if this detection is near an existing flower.
    """
    for (fx, fy) in flower_visit_counts.keys():
        dist = math.sqrt((x - fx) ** 2 + (y - fy) ** 2)
        if dist < FLOWER_MATCH_THRESHOLD:
            return (fx, fy)
    return None

def is_daytime():
    hour = datetime.now().hour
    return 6 <= hour < 18   # simple version

# ==========================================
# PROCESS FILE
# ==========================================
def process_file(filepath, camera_data=None):
    new_positions = []
    if not os.path.exists(filepath):
        return new_positions

    print(f"\n========== EVENT PROCESSING FILE: {os.path.basename(filepath)} ==========")
    use_camera = is_daytime() and camera_data is not None

    if use_camera:
        print("[FUSION MODE] DAY → Confidence Fusion (Camera vs LiDAR)")
    else:
        print("[FUSION MODE] NIGHT → LiDAR Only")

    print(f"{'EVENT_ID':<15} {'SOURCE':<12} {'PREDICTION':<12} {'CONFIDENCE':<10} {'STATUS'}")
    print("-" * 70)
        
    with open(filepath, "r") as f:
        for line in f:
            if not line.strip(): 
                continue

            event = json.loads(line)

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

            if camera_data:
                cam = camera_data[0]
                camera_conf = cam.get("confidence", 0.0)
                camera_is_bee = cam.get("pollinator", False)
            
            # ======================================
            # LOG BOTH SOURCES
            # ======================================
            print(f"{str(event_id):<15} {'LIDAR':<10} "
                  f"{'pollinator' if lidar_is_bee else 'not_pollinator':<18} "
                  f"{lidar_conf:0.3f}          -")

            if camera_data:
                print(f"{str(event_id):<15} {'CAMERA':<10} "
                      f"{'pollinator' if camera_is_bee else 'not_pollinator':<18} "
                      f"{camera_conf:0.3f}          -")
                            
            # ======================================
            # FUSION LOGIC
            # ======================================
            if use_camera:
                if camera_conf >= lidar_conf:
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

            print(f"{str(event_id):<15} {source:<10} "
                  f"{'pollinator' if is_bee else 'not_pollinator':<18} "
                  f"{final_conf:0.3f}          {status}")

            print("-" * 70)

            if not is_bee:
                continue

            # ======================================
            # POSITION COMPUTATION
            # ======================================
            angles = event["angles"]
            distance_series = event["distance_series"]
            if not angles or not distance_series:
                print("[WARNING] Missing angles or distance_series")
                continue

            avg_distances = np.mean(distance_series, axis=0)

            xs = []
            ys = []

            for angle_index, distance in zip(angles, avg_distances):
                x, y = polar_to_xy(distance, angle_index)
                xs.append(x)
                ys.append(y)

            new_positions.append((np.mean(xs), np.mean(ys)))
    
    return new_positions

# ==========================================
# MAIN HEATMAP GENERATOR
# ==========================================
def generate_heatmap_png(filepath, camera_data=None):

    new_positions = process_file(filepath, camera_data)

    # ==========================================
    # UPDATE GLOBAL FLOWER COUNTS
    # ==========================================
    for x, y in new_positions:
        existing = find_existing_flower(x, y)
        if existing:
            flower_visit_counts[existing] += 1
        else:
            flower_visit_counts[(x, y)] = 1

    # if len(flower_visit_counts) == 0:
    #     return None
    pollinator_detected = len(new_positions) > 0
    detection_json_bytes = json.dumps({"pollinator_detected": pollinator_detected}).encode("utf-8")

    if len(flower_visit_counts) == 0:
        return None, detection_json_bytes
    
    xs = []
    ys = []
    counts = []

    for (x, y), count in flower_visit_counts.items():
        xs.append(x)
        ys.append(y)
        counts.append(count)

    total_visits = sum(counts)
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
    ax.set_title(f"Pollinator Activity Map\nTotal Visits: {total_visits}")
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

    # ==========================================
    # ALSO RETURN PNG BYTES FOR NETWORK
    # ==========================================
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=300)
    plt.close(fig)

    buffer.seek(0)
    return buffer.read(), detection_json_bytes
