# train_model.py

import os
import json
import numpy as np
import joblib
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.utils import shuffle

from feature_extractor import extract_features

DATASET_PATH = "dataset/deduped_dataset" # "new_labeled_dataset"
MODEL_PATH = "models/bee_model4.pkl"

# Must match extract_features() return list indices 1:-1 exactly
FEATURE_NAMES = [
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
]

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
        y.append(1 if event["label"] == "bee" else 0) # convert label to number

    return np.array(X), np.array(y)

def train():

    os.makedirs("features", exist_ok=True)
    os.makedirs("models", exist_ok=True)

    X, y = load_dataset()

    if len(X) == 0:
        print("No data found to train on. Check your labeled_dataset folder.")
        return  
    
    # dataset overview
    print(f"Dataset folder: {DATASET_PATH}")
    print("Dataset size:", len(X))
    print("Bee samples:", sum(y))
    print("Not bee samples:", len(y) - sum(y))

    # =========================================================
    # CROSS-VALIDATION — honest performance estimate
    # Do this BEFORE fitting on full data.
    # =========================================================
    X_s, y_s = shuffle(X, y, random_state=42)
 
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    # 1. Define the model FIRST (this serves as the template for CV)
    model_cv = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=42
    )
    
    # 2. Pass model_cv as the first argument
    cv_f1  = cross_val_score(model_cv, X_s, y_s, cv=cv, scoring="f1")
    cv_acc = cross_val_score(model_cv, X_s, y_s, cv=cv, scoring="accuracy")
 
    print("\n" + "=" * 50)
    print("CROSS-VALIDATION RESULTS (honest performance)")
    print("=" * 50)
    print(f"  F1  per fold:  {[f'{s:.3f}' for s in cv_f1]}")
    print(f"  F1  mean ± std: {cv_f1.mean():.3f} ± {cv_f1.std():.3f}")
    print(f"  Acc per fold:  {[f'{s:.3f}' for s in cv_acc]}")
    print(f"  Acc mean ± std: {cv_acc.mean():.3f} ± {cv_acc.std():.3f}")
 
    if cv_f1.mean() >= 0.90:
        print("  ✅ Model looks solid. Deploy with confidence.")
    elif cv_f1.mean() >= 0.80:
        print("  ⚠️  Acceptable but collect more diverse data.")
    else:
        print("  ❌ Low performance. More data and feature work needed.")
    print("=" * 50)

    # =========================================================
    # TRAIN FINAL MODEL ON FULL DATASET
    # =========================================================
    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=42
    )
    model.fit(X_s, y_s)

    # =========================================================
    # FEATURE IMPORTANCE
    # =========================================================
    importances = model.feature_importances_
    indices     = np.argsort(importances)[::-1]
 
    print("\n" + "=" * 30)
    print("FEATURE IMPORTANCE LOG")
    print("=" * 30)
    for i in indices:
        name  = FEATURE_NAMES[i]
        score = importances[i]
        bar   = "█" * int(score * 50)
        print(f"{name:<25} | {score:.4f} {bar}")
    print("=" * 30 + "\n")
 
    plt.figure(figsize=(12, 7))
    plt.title("LiDAR Feature Importance for Bee Detection (SICKSense)")
    plt.bar(range(len(importances)), importances[indices], color="forestgreen", align="center")
    plt.xticks(range(len(importances)), [FEATURE_NAMES[i] for i in indices], rotation=45, ha="right")
    plt.ylabel("Relative Importance Score")
    plt.xlabel("LiDAR Signal Features")
    plt.tight_layout()
    plt.savefig("features/feature_importance.png")
    print("[SUCCESS] Feature importance graph saved as 'features/feature_importance.png'")
    plt.show()

    # =========================================================
    # FEATURE SCATTER PLOT
    # Uses the two highest-importance features from last run.
    # Update indices here if importance ranking changes.
    # mean_intrusion = index 8, mean_distance = index 5
    # =========================================================
    # Re-calculate indices based on the trained model's importances
    importances = model.feature_importances_
    top_two_indices = np.argsort(importances)[-2:] # Get indices of two highest scores
    
    idx_y = top_two_indices[-1] # Most important
    idx_x = top_two_indices[-2] # Second most important

    plt.figure(figsize=(8, 6))

    # Filter data for plotting
    for label, color, name in [(1, "tab:blue", "bee"), (0, "tab:orange", "not_bee")]:
        mask = (y_s == label)
        plt.scatter(
            X_s[mask, idx_x], 
            X_s[mask, idx_y], 
            label=name, 
            alpha=0.6, 
            edgecolors='w'
        )
    
    plt.xlabel(FEATURE_NAMES[idx_x])
    plt.ylabel(FEATURE_NAMES[idx_y])
    plt.title(f"Top 2 Features: {FEATURE_NAMES[idx_y]} vs {FEATURE_NAMES[idx_x]}")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.savefig("features/new_feature_scatter.png")
    print(f"[SUCCESS] Scatter plot updated using {FEATURE_NAMES[idx_y]} and {FEATURE_NAMES[idx_x]}")
    plt.show()
    
    # =========================================================
    # TRAINING PERFORMANCE (sanity check — should be ~100%)
    # =========================================================
    preds = model.predict(X_s)
    print("\nTraining Performance (on full dataset — expect ~100%)")
    print(classification_report(y_s, preds))
 
    # =========================================================
    # SAVE MODEL
    # =========================================================
    joblib.dump(model, MODEL_PATH)
    print("Model saved to:", MODEL_PATH)
 
 
if __name__ == "__main__":
    train()