# ECEN 404 / ECEN 403 — Team 33 Pollination Monitoring System (AgriPollinate)

## Overview

AgriPollinate is a smart pollination monitoring system designed to help farmers track pollinator activity in real time. Traditional monitoring methods are manual, slow, and not scalable. This system automates the process using LiDAR sensing, image-based machine learning, and live dashboard visualization.

The system detects when insects interact with flowers, classifies them as pollinators or non-pollinators, and displays results through a live dashboard with heatmap visualization.

---

## System Architecture

The system is composed of multiple integrated subsystems working together in an end-to-end pipeline from detection to visualization:

| Subsystem | Folder | Description |
|-----------|--------|-------------|
| LiDAR Processing & ML | `lidar_ML/` | Motion detection, feature extraction, Random Forest classification |
| Image Classification | `image_ML/` | YOLOv8-based insect detection via FastAPI backend |
| Raspberry Pi Control | `pi_program/` | Hardware coordination and event pipeline triggering |
| LiDAR Client | `lidar_client_communication/` | LiDAR data streaming and event generation |
| Communication Layer | `communication_protocol.py` | Structured packet-based messaging between subsystems |
| Web Dashboard | `agripollinate_webpage/` | Real-time detection results and heatmap visualization |
| Power / Hardware | `board_v1_files/`, `board_v2_file/` | Custom PCB designs for solar power management |
| Enclosure | `enclosing_v1_stl/` | 3D-printed housing structure |

---

## Data Flow

```
LiDAR detects motion near flower
          ↓
Event generated with flower ID + timestamp
          ↓
Camera captures corresponding image
          ↓
Image ML model classifies insect (YOLOv8)
          ↓
LiDAR ML model validates classification (Random Forest)
          ↓
Sensor fusion merges both results
          ↓
Data sent to dashboard via TCP communication layer
          ↓
Heatmap updated in real time
```

---

## Key Features

- Real-time pollinator detection at the flower level
- LiDAR-based motion analysis with ML classification
- YOLOv8 image-based insect detection
- Random Forest LiDAR model with ~92% cross-validation F1 score
- Sensor fusion between camera and LiDAR subsystems
- TCP-based structured packet communication
- Live heatmap dashboard visualization
- Custom dataset collected from real hardware deployment
- Batch data collection pipeline for model retraining

---

## Machine Learning Components

### LiDAR Model (`lidar_ML/`)
- **Algorithm:** Random Forest classifier
- **Input:** Feature vectors extracted from LiDAR scan sequences
- **Output:** `pollinator` / `non-pollinator` + confidence score
- **Performance:** ~92% cross-validation F1 score

### Image Model (`image_ML/`)
- **Algorithm:** YOLOv8 object detection
- **Input:** Camera frames triggered by LiDAR events
- **Output:** Bounding box + insect class label
- **Backend:** FastAPI inference server

---

## Dataset

Both ML models use custom datasets collected from real hardware tests in the deployment environment:

- Bees
- Butterflies
- Ladybugs
- Beetles
- Grasshoppers
- Environmental noise / non-insect motion

LiDAR event data is stored in `lidar_ML/dataset/`. Image data is managed within `image_ML/`.

---

## Hardware

- Raspberry Pi 5
- LiDAR sensor module
- Camera module
- Custom PCB (v1 and v2 designs)
- Solar power management system
- 3D-printed enclosure housing

---

## Communication Protocol

All subsystems communicate using a structured packet format defined in [`communication_protocol.py`](communication_protocol.py). Key packet types include:

- `PACKET_ID_LIDAR_OUTGOING` — LiDAR event data from the sensor
- `PACKET_ID_IMAGE_RESPONSE` — Image classification result from the camera subsystem
- `PACKET_ID_LIDAR_RESPONSE` — LiDAR ML classification result

---

## Folder Structure

```
ECEN404_403_Team_33_Pollination_Monitoring-Internal/
│
├── lidar_ML/                      # LiDAR ML subsystem (see lidar_ML/README.md)
├── image_ML/                      # Image-based ML detection subsystem
├── lidar_client_communication/    # LiDAR data streaming client
├── pi_program/                    # Raspberry Pi hardware control
├── communication_protocol.py      # Shared packet communication layer
├── agripollinate_webpage/         # Web dashboard frontend
│
├── board_v1_files/                # PCB v1 design files
├── board_v2_file/                 # PCB v2 design files
├── enclosing_v1_stl/              # 3D enclosure STL files
│
├── 403_presentations/             # ECEN 403 presentation materials
├── presentations_404/             # ECEN 404 presentation materials
│
└── README.md                      # This file
```

---

## System Improvements (ECEN 403 → ECEN 404)

- Switched from rule-based scan logic to ML-based LiDAR classification
- Replaced cloud communication with TCP-based local system
- Improved dataset quality and removed duplicate/noisy samples
- Added sensor fusion between LiDAR and camera subsystems
- Improved real-time synchronization between subsystems
- Introduced structured packet communication protocol
- Built full end-to-end automated detection pipeline

---

## Results

- ~92% pollinator classification accuracy on held-out test set
- Reliable real-time detection pipeline with low latency
- Stable sensor fusion logic across LiDAR and camera
- Successful full system integration and deployment testing

---

## Future Improvements

- Add long-term database storage for historical activity tracking
- Improve model performance on edge cases and rare insect types
- Expand dataset with more environmental and lighting variations
- Optimize real-time inference speed for embedded deployment
- Improve dashboard analytics and user-facing reporting
- Deploy cloud backup system for data redundancy

---

## Team

ECEN 403 / ECEN 404 — Team 33
SICKSense PathFinder AgriPollinate
- [`Paavan Bagla`](https://github.com/PaavanBagla)
- [`Josiah Faircloth`](https://github.com/Josiahtate-tamu)
- [`Jason Agnew`](https://github.com/oops23)
- [`Samuel Ramos`](https://github.com/samwr-1)

Texas A&M University
