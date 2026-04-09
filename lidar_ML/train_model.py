# train_model.py

import os
import json
import numpy as np
import joblib
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.utils import shuffle

from feature_extractor import extract_features

DATASET_PATH = "dataset/new_labeled_dataset"
MODEL_PATH = "models/bee_model4.pkl"

def load_dataset():
    """
    Loads JSON events, extracts features using the feature_extractor,
    and prepares them for the Random Forest model.
    """
    X = []
    y = []

    if not os.path.exists(DATASET_PATH):
        print(f"Error: {DATASET_PATH} folder not found.")
        return np.array([]), np.array([])
    
    for filename in os.listdir(DATASET_PATH):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(DATASET_PATH, filename)

        with open(filepath, "r") as f:
            event = json.load(f)

        # Skip events without labels
        if event["label"] is None:
            continue
        
        # Extract features using your feature_extractor.py logic
        features = extract_features(event)

        # remove non-numeric fields (Index 0 is event_id, Index -1 is label)
        numeric_features = features[1:-1]

        X.append(numeric_features)

        # convert label to number
        if event["label"] == "bee":
            y.append(1)
        else:
            y.append(0)

    return np.array(X), np.array(y)


def train():

    os.makedirs("features", exist_ok=True)
    os.makedirs("models", exist_ok=True)

    X, y = load_dataset()

    if len(X) == 0:
        print("No data found to train on. Check your labeled_dataset folder.")
        return
    
    print("Dataset size:", len(X))
    print("Bee samples:", sum(y))
    print("Not bee samples:", len(y) - sum(y))
    
    # =========================================================
    # FEATURE SCATTER PLOT
    # =========================================================
    # Using the two most important features discovered earlier
    mean_intrusion_idx = 8
    mean_distance_idx = 5

    bee_x = []
    bee_y = []

    notbee_x = []
    notbee_y = []

    for i in range(len(X)):

        if y[i] == 1:
            bee_x.append(X[i][mean_distance_idx])
            bee_y.append(X[i][mean_intrusion_idx])
        else:
            notbee_x.append(X[i][mean_distance_idx])
            notbee_y.append(X[i][mean_intrusion_idx])

    plt.figure(figsize=(8,6))
    plt.scatter(bee_x, bee_y, label="bee", alpha=0.7)
    plt.scatter(notbee_x, notbee_y, label="not_bee", alpha=0.7)
    plt.xlabel("mean_distance")
    plt.ylabel("mean_intrusion")
    plt.title("Feature Separation: Bee vs Not Bee")
    plt.legend()
    plt.savefig("features/feature_scatter.png")
    print("[SUCCESS] Feature scatter plot saved as 'features/feature_scatter.png'")
    plt.show()

    # =========================================================
    # MODEL TRAINING
    # =========================================================
    # Shuffle to ensure the model doesn't learn based on file order
    X, y = shuffle(X, y, random_state=42)

    # Initialize and train the Random Forest
    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=42
    )

    model.fit(X, y)

    # =========================================================
    # FEATURE IMPORTANCE ANALYSIS
    # =========================================================
    # This list MUST match the order of features[1:-1] in extract_features()
    feature_names = [
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
    ]

    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]  # Sort from highest importance to lowest

    # =========================================================
    # TERMINAL VISUALIZATION
    # =========================================================
    print("\n" + "="*30)
    print("FEATURE IMPORTANCE LOG")
    print("="*30)
    for i in indices:
        name = feature_names[i]
        score = importances[i]
        # Create a simple text-based bar for quick visual reference
        bar = "█" * int(score * 50) 
        print(f"{name:<20} | {score:.4f} {bar}")
    print("="*30 + "\n")

    # =========================================================
    # MATPLOTLIB VISUALIZATION
    # =========================================================
    plt.figure(figsize=(12, 7))
    plt.title("LiDAR Feature Importance for Bee Detection (SICKSense)")
    plt.bar(range(len(importances)), importances[indices], color='forestgreen', align="center")
    plt.xticks(range(len(importances)), [feature_names[i] for i in indices], rotation=45, ha='right') # Label the X-axis with the feature names
    plt.ylabel("Relative Importance Score")
    plt.xlabel("LiDAR Signal Features")
    plt.tight_layout()
    plt.savefig("features/feature_importance.png")
    print("\n[SUCCESS] Feature importance graph saved as 'features/feature_importance.png'")
    plt.show()

    # =========================================================
    # TRAINING PERFORMANCE
    # =========================================================
    # Evaluate on the training set
    preds = model.predict(X)

    print("\nTraining Performance")
    print(classification_report(y, preds))

    # =========================================================
    # SAVE MODEL
    # =========================================================    
    joblib.dump(model, MODEL_PATH)
    print("Model saved to:", MODEL_PATH)

if __name__ == "__main__":
    train()