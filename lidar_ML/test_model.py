import os
import json
from sklearn.metrics import confusion_matrix
import matplotlib.pyplot as plt
import numpy as np
from bee_classifier import BeeClassifier

DATASET_PATH = "test_dataset"
MODEL_PATH = "models/bee_model4.pkl"

classifier = BeeClassifier(MODEL_PATH)

correct = 0
total = 0
y_true = []
y_pred = []

print(f"\nTesting Model: {MODEL_PATH}\n")
print(f"{'FILE':40} {'ACTUAL':10} {'PREDICTED':10} {'BEE_PROB':10} RESULT")
print("-"*80)

for filename in os.listdir(DATASET_PATH):

    if not filename.endswith(".json"):
        continue

    filepath = os.path.join(DATASET_PATH, filename)

    with open(filepath, "r") as f:
        event = json.load(f)

    actual = event["label"]

    prediction, prob = classifier.predict(event)

    y_true.append(1 if actual == "bee" else 0)
    y_pred.append(1 if prediction == "bee" else 0)

    result = "✅"

    if prediction != actual:
        result = "❌"
    else:
        correct += 1

    total += 1

    print(f"{filename:40} {actual:10} {prediction:10} {prob:0.2f}      {result}")

print("\n" + "-"*80)

accuracy = correct / total

print(f"Total events: {total}")
print(f"Correct predictions: {correct}")
print(f"Accuracy: {accuracy:.2%}")
cm = confusion_matrix(y_true, y_pred)

plt.imshow(cm)
plt.title("Confusion Matrix")
plt.xlabel("Predicted")
plt.ylabel("Actual")

plt.xticks([0,1], ["not_bee","bee"])
plt.yticks([0,1], ["not_bee","bee"])

for i in range(2):
    for j in range(2):
        plt.text(j, i, cm[i,j], ha="center", va="center")

plt.colorbar()
plt.show()