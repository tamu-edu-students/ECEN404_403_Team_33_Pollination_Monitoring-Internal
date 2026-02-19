# SICKSense Agripollinate Pi Program

This folder contains the Raspberry Pi master-side runtime for flower-visit event detection, image capture, and bidirectional packet routing between image and LiDAR clients.

## Updated Program Structure

The architecture has been refactored from the earlier object-tracking layout into an event-driven, flower-centric pipeline:

1. LiDAR stream is read in real time.
2. Flower occupancy is detected with per-flower thresholds and confirmation windows.
3. Event start triggers image burst capture/transmission.
4. Event end packages visit data for LiDAR data client transmission.
5. Master forwards response packets between image and LiDAR clients using a shared protocol.

## Files

### Core Runtime Modules

- **`master_main.py`**
     - Main orchestrator for all subsystems.
     - Handles startup/shutdown, watchdog checks, testing mode, event callbacks, and cross-server linking.

- **`lidar_parser.py`**
     - Manages TCP connection to the SICK LiDAR scanner.
     - Parses `LMDscandata` telegrams.
     - Supports selective index parsing so only required flower angle indices are decoded for detection.

- **`event_detector.py`**
     - Performs flower visit detection from scan data.
     - Uses configured flower angle indices + background distances.
     - Emits `start` and `end` events with distance history and metadata.

- **`image_capture.py`**
     - Runs image server socket and captures images via `fswebcam`.
     - Sends image data with packet headers (`1050`) and receives image-client responses (`2050`).
     - Forwards responses to the LiDAR data server when connected.

- **`lidar_data_server.py`**
     - Runs LiDAR data server socket for event payload delivery.
     - Sends event packets (`1025`) and handles LiDAR-client responses (`2025`).
     - Forwards responses to the image server when connected.

- **`communication_protocol.py`**
     - Defines packet header/payload format, serialization, and parsing.
     - Defines packet IDs used by both server paths (`1025`, `1050`, `2025`, `2050`).
     - Provides shared event ID helpers.

### Setup / Utility Module

- **`flower_setup.py`**
     - One-time/setup tool to build flower configuration from baseline scans.
     - Produces flower angle indices and background distances for use by the event detector.

### Data Directories

- **`image_downloads/`** - local image output/download area.
- **`lidar_downloads/`** - local LiDAR/event data output/download area.

## High-Level Data Flow

```text
LiDAR Scanner
          -> lidar_parser
          -> event_detector
                -> on start: image_capture (send 1050 packets)
                -> on end:   lidar_data_server (send 1025 packets)

Image client response (2050)
          -> image_capture
          -> forwarded to lidar_data_server / LiDAR client

LiDAR client response (2025)
          -> lidar_data_server
          -> forwarded to image_capture / Image client
```

## Key Configuration (master_main.py)

- **LiDAR Connection**: `LIDAR_HOST`, `LIDAR_PORT`
- **Image Server**: `IMAGE_SERVER_HOST`, `IMAGE_SERVER_PORT`, `IMAGE_SAVE_DIR`, `IMAGE_RESOLUTION`, `BURST_SIZE`
- **LiDAR Data Server**: `LIDAR_DATA_HOST`, `LIDAR_DATA_PORT`, `LIDAR_DATA_SAVE_DIR`
- **Event Detection**: `EVENT_DIST_THRESHOLD`, `EVENT_START_CONFIRM_SCANS`, `EVENT_END_CONFIRM_SCANS`
- **Reliability**: `WATCHDOG_TIMEOUT`, `CONNECTION_TIMEOUT`

## Running

On Raspberry Pi (master):

```bash
cd pi_program
python3 master_main.py
```

## Dependencies

Python standard library only for core runtime modules.

System dependency for image capture:

- `fswebcam` (example install on Debian/Raspberry Pi OS):

```bash
sudo apt-get install fswebcam
```

## Change Summary vs Previous Structure

- Replaced legacy object-tracking-centric flow with flower visit event detection.
- Added/standardized packet-based cross-client protocol support through `communication_protocol.py`.
- Added dedicated LiDAR data server path via `lidar_data_server.py`.
- Added setup utility `flower_setup.py` for deriving flower index/background configuration.
- Updated LiDAR parse path to support selective index decoding for lower per-scan processing load.
