# heatmap_generator.py

import io
import json
import numpy as np
import matplotlib.pyplot as plt
import math
from datetime import datetime
import os
from lidar_ML.bee_classifier import BeeClassifier

ANGLE_START_DEG = 0.0
ANGLE_INCREMENT_DEG = 0.5

classifier = BeeClassifier()

# ==========================================
# GLOBAL STORAGE FOR ACCUMULATED VISITS
# ==========================================
# key = (rounded_x, rounded_y)
# value = visit count
flower_visit_counts = {}

# distance threshold to consider same flower
FLOWER_MATCH_THRESHOLD = 0.15  # meters


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


def process_file(filepath):
    new_positions = []

    with open(filepath, "r") as f:
        for line in f:
            event = json.loads(line)
            is_bee = classifier.predict(event)

            if not is_bee:
                continue

            angles = event["angles"]
            distance_series = event["distance_series"]
            avg_distances = np.mean(distance_series, axis=0)

            xs = []
            ys = []

            for angle_index, distance in zip(angles, avg_distances):
                x, y = polar_to_xy(distance, angle_index)
                xs.append(x)
                ys.append(y)

            new_positions.append((np.mean(xs), np.mean(ys)))

    return new_positions

def generate_heatmap_png(filepath):

    new_positions = process_file(filepath)

    # ==========================================
    # UPDATE GLOBAL FLOWER COUNTS
    # ==========================================
    for x, y in new_positions:

        existing = find_existing_flower(x, y)

        if existing:
            flower_visit_counts[existing] += 1
        else:
            flower_visit_counts[(x, y)] = 1

    if len(flower_visit_counts) == 0:
        return None

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

    ax.set_title(
        f"Pollinator Activity Map\nTotal Visits: {total_visits}"
    )

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
    return buffer.read()
