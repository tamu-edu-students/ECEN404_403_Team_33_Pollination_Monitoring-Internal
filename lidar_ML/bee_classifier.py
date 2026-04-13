# bee_classifier.py

from pyexpat import features

import joblib
import os
from feature_extractor import extract_features

class BeeClassifier:
    def __init__(self, model_path, threshold=0.45):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at: {model_path}")
        # load trained model
        self.model = joblib.load(model_path)
        self.threshold = threshold

    def predict(self, event):
        duration = event.get("end_time", 0) - event.get("start_time", 0)
        num_scans = event.get("num_scans", 0)
        background = event.get("background_dist", 1.0)
        all_distances = [d for scan in event["distance_series"] for d in scan]
        max_intrusion = background - min(all_distances)

        # After — give a small buffer above your longest bee event (8.87s)
        # if duration > 10.0:
        #     print(f"[PRE-FILTER] Rejected: duration={duration:.2f}s > 10.0s")
        #     return "not_bee", 0.0
        # if num_scans > 150:
        #     print(f"[PRE-FILTER] Rejected: num_scans={num_scans} > 150")
        #     return "not_bee", 0.0
    
        # extract features from event
        features = extract_features(event)

        # remove non-numeric fields (Index 0 is event_id, Index -1 is label)
        numeric_features = features[1:16]   # indices 1–15, drop event_id (0) and label (16)
        # numeric_features = features[1:-1]

        # model expects 2D input
        lidar_conf = self.model.predict_proba([numeric_features])[0][1]

        if lidar_conf > self.threshold:
            label = "bee"
        else:
            label = "not_bee"

        return label, lidar_conf