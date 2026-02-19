""" SICKSense Agripollinate Master Program Version 2.0
    Created by:    Josiah Faircloth
    date:    01/28/2026

    Master control program integrating LiDAR object detection and image capture.
    Maintains dual TCP connections: one to LiDAR scanner, one to image client.
    Implements bidirectional packet-based communication protocol with cross-client
    message routing and event-based coordination.
"""

import time
import signal
import sys
import os
import threading
from datetime import datetime
from lidar_parser import LidarConnection
from event_detector import EventDetector
from image_capture import ImageServer
from lidar_data_server import LidarDataServer

# Adds the parent directory to the search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from communication_protocol import generate_event_id, Packet, PacketHeader, PACKET_ID_LIDAR_OUTGOING
import json


# -------------------------------
# Configuration Parameters
# -------------------------------

# LiDAR Configuration
LIDAR_HOST = "169.254.251.84"
LIDAR_PORT = 2112

# Image Server Configuration
IMAGE_SERVER_HOST = '0.0.0.0'
IMAGE_SERVER_PORT = 12345 
IMAGE_SAVE_DIR = "/home/josiah/pi_program/captured_images"
IMAGE_RESOLUTION = '640x480' # max resolution: 3264x2448, default: 640x480
BURST_SIZE = 5  # Number of images to capture per trigger

# LiDAR Data Server Configuration
LIDAR_DATA_HOST = '0.0.0.0'
LIDAR_DATA_PORT = 12346
LIDAR_DATA_SAVE_DIR = "/home/josiah/pi_program/lidar_data"
TRIGGER_SCANS_TO_SAVE = 10  # Number of scans to save per trigger

# Event Detection Configuration
EVENT_DIST_THRESHOLD = 0.03  # Distance threshold for occupancy detection (meters)
EVENT_START_CONFIRM_SCANS = 5
EVENT_END_CONFIRM_SCANS = 5

# Watchdog Configuration
WATCHDOG_TIMEOUT = 5.0          # Maximum time between scans before watchdog alert (seconds)

# Connection Timeout Configuration
CONNECTION_TIMEOUT = 5.0       # Timeout for connection attempts before prompting user (seconds)


# -------------------------------
# Global State
# -------------------------------
running = True
last_scan_time = None
testing_mode = False            # Flag for LiDAR scanner testing mode
lidar_data_client_enabled = True # Flag for LiDAR data client availability


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\n[SHUTDOWN] Received interrupt signal, shutting down...")
    running = False


def watchdog_check(current_time):
    """Check if LiDAR data stream is still active"""
    global last_scan_time
    
    if last_scan_time is None:
        return True  # First scan, no issue
    
    time_since_last_scan = current_time - last_scan_time
    
    if time_since_last_scan > WATCHDOG_TIMEOUT:
        print(f"[WATCHDOG] WARNING: No LiDAR data for {time_since_last_scan:.2f}s!")
        return False
    
    return True


def prompt_user_input(prompt_text, timeout_seconds=30.0):
    """
    Display a prompt and get user input with timeout.
    Returns the user's response (lowercase) or None if timeout.
    """
    response = [None]
    
    def get_input():
        try:
            user_input = input(prompt_text)
            response[0] = user_input.lower().strip()
        except EOFError:
            response[0] = None
    
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()
    input_thread.join(timeout=timeout_seconds)
    
    if response[0] is None:
        print("[TIMEOUT] No response received within time limit.")
    
    return response[0]


def connect_lidar_with_timeout(host, port):
    """
    Attempt to connect to LiDAR scanner with timeout and user prompt.
    Returns (lidar_connection, testing_mode_enabled) tuple.
    testing_mode_enabled is True if user chose to run in testing mode.
    """
    global testing_mode
    
    lidar = LidarConnection(host=host, port=port)
    
    if not lidar.connect(timeout=CONNECTION_TIMEOUT):

        user_response = prompt_user_input(
            "Would you like to run the device in testing mode? (y/n): ",
            timeout_seconds=30
        )
    
        if user_response == 'y':
            print("[INIT] Running in TESTING MODE - LiDAR scanner disabled, awaiting user input for event triggers")
            testing_mode = True
            return None, True  # No LiDAR connection, testing mode enabled
        else:
            print("[INIT] Continuing to attempt LiDAR connection...")
            return connect_lidar_with_timeout(host, port)  # Retry
        
    return lidar, False


def connect_lidar_data_server_with_timeout(lidar_data_server):
    """
    Wait for LiDAR data client connection with timeout and user prompt.
    Returns True if client is expected to connect, False if user skipped waiting.
    """
    global lidar_data_client_enabled
    
    if not lidar_data_server.start_server(timeout=CONNECTION_TIMEOUT):

        user_response = prompt_user_input(
            "Would you like to continue without a LiDAR Data client? (y/n): ",
            timeout_seconds=30
        )
    
        if user_response == 'y':
            print("[INIT] Continuing without LiDAR Data client - image capture only mode")
            lidar_data_client_enabled = False
            return False  # Skip waiting, continue without client
        else:
            print("[INIT] Continuing to attempt LiDAR data client connection...")
            return connect_lidar_data_server_with_timeout(lidar_data_server)  # Retry
    
    lidar_data_client_enabled = True
    return True


def _handle_event_start_async(event, event_count, image_server):
    """
    Background worker for event start handling.
    Runs in separate thread to avoid blocking main LiDAR processing loop.
    """
    flower_id = event["flower_id"]
    start_time = event["start_time"]
    
    # Generate event ID from the event start timestamp
    event_id = generate_event_id(start_time)
    
    print(f"[ALERT] Flower visit #{event_count} started at flower {flower_id} at {start_time:.2f}s")
    print(f"[EVENT] Event ID generated: {event_id}")
    
    # Trigger image capture burst with event ID and packet-based protocol
    if image_server and image_server.connected:
        print(f"[EVENT {event_id}] Sending image burst to image client...")
        # Capture images and send with packet protocol
        image_paths = []
        for i in range(BURST_SIZE):
            image_path = image_server.capture_image()
            if image_path:
                image_paths.append(image_path)
        
        if image_paths:
            image_server.send_images_with_packet(event_id, image_paths)
            print(f"[EVENT {event_id}] Successfully sent {len(image_paths)} images")
        else:
            print(f"[EVENT {event_id}] Failed to capture any images")
    else:
        print("[WARNING] Image server not connected, skipping image capture")


def on_event_start(event, event_count, image_server):
    """
    Callback function triggered when flower visit event starts.
    Spawns background thread to handle blocking operations.
    """
    # Offload to background thread to avoid blocking main scan processing
    worker = threading.Thread(
        target=_handle_event_start_async,
        args=(event, event_count, image_server),
        daemon=True
    )
    worker.start()


def _handle_event_end_async(event, lidar_data_server, lidar_data_client_enabled):
    """
    Background worker for event end handling.
    Runs in separate thread to avoid blocking main LiDAR processing loop.
    """
    flower_id = event["flower_id"]
    end_time = event["end_time"]
    
    # Generate event ID from the event start timestamp
    event_id = generate_event_id(event["start_time"])
    
    print(f"[ALERT] Flower visit ended for {flower_id} at {end_time:.2f}s")
    print(f"[EVENT {event_id}] Processing event end data...")
    
    # Send event data to LiDAR data client if enabled
    if lidar_data_client_enabled and lidar_data_server and lidar_data_server.connected:
        print(f"[EVENT {event_id}] Sending event data to LiDAR client...")
        
        # Prepare event data for transmission
        event_data = json.dumps({
            "event_type": event.get("event_type", "flower_visit"),
            "event_id": event_id,
            "flower_id": event["flower_id"],
            "start_time": event["start_time"],
            "end_time": event["end_time"],
            "num_scans": event["num_scans"],
            "angles": event["angles"],
            "distance_series": event["distance_series"],
            "timestamp": datetime.now().isoformat()
        }).encode('utf-8')
        
        header = PacketHeader(event_id, PACKET_ID_LIDAR_OUTGOING)
        packet = Packet(header, event_data)
        
        try:
            serialized = packet.serialize()
            lidar_data_server.client_socket.sendall(serialized)
            print(f"[EVENT {event_id}] Successfully sent event data packet")
        except Exception as e:
            print(f"[EVENT {event_id}] Failed to send event data: {e}")
    elif not lidar_data_client_enabled:
        print("[INFO] LiDAR data client disabled, skipping event data transmission")
    else:
        print("[WARNING] LiDAR data server not connected, skipping event data transmission")


def on_event_end(event, lidar_data_server):
    """
    Callback function triggered when flower visit event ends.
    Spawns background thread to handle blocking operations.
    """
    global lidar_data_client_enabled
    
    # Offload to background thread to avoid blocking main scan processing
    worker = threading.Thread(
        target=_handle_event_end_async,
        args=(event, lidar_data_server, lidar_data_client_enabled),
        daemon=True
    )
    worker.start()


def main():
    """
    Master main function coordinating all subsystems.
    """
    global running, last_scan_time, testing_mode, lidar_data_client_enabled
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    print("="*60)
    print("SICKSense Agripollinate Master Program")
    print("Version 2.0 - January 28, 2026")
    print("="*60)
    
    # Initialize components
    lidar = None
    image_server = None
    lidar_data_server = None
    detector = None
    object_count = 0
    
    try:
        # 1. Connect to LiDAR with timeout and testing mode support
        print("\n[INIT] Initializing LiDAR connection...")
        lidar, testing_mode = connect_lidar_with_timeout(LIDAR_HOST, LIDAR_PORT)
        
        if lidar is None and not testing_mode:
            print("[ERROR] Failed to initialize LiDAR connection. Exiting.")
            return
        
        # 2. Start image server
        print("\n[INIT] Starting image server...")
        image_server = ImageServer(
            host=IMAGE_SERVER_HOST, 
            port=IMAGE_SERVER_PORT,
            save_dir=IMAGE_SAVE_DIR,
            resolution=IMAGE_RESOLUTION
        )
        if not image_server.start_server():
            print("[ERROR] Failed to start image server. Exiting.")
            if not lidar is None:
                lidar.disconnect()
            return
        
        # 3. Start LiDAR data server
        print("\n[INIT] Starting LiDAR data server...")
        lidar_data_server = LidarDataServer(
            host=LIDAR_DATA_HOST,
            port=LIDAR_DATA_PORT,
            save_dir=LIDAR_DATA_SAVE_DIR
        )
        connect_lidar_data_server_with_timeout(lidar_data_server)
        
        # Link servers for cross-client message routing
        print("\n[INIT] Linking servers for cross-client communication...")
        image_server.lidar_server = lidar_data_server
        lidar_data_server.image_server = image_server
        if lidar_data_client_enabled:
            print("[INIT] Cross-client routing enabled (Image <-> LiDAR)")
        else:
            print("[INIT] Cross-client routing: Image client only (LiDAR client disabled)")
        
        # 4. Initialize event detector
        print("\n[INIT] Initializing event detector...")
        detector = EventDetector(
            dist_threshold=EVENT_DIST_THRESHOLD,
            start_confirm_scans=EVENT_START_CONFIRM_SCANS,
            end_confirm_scans=EVENT_END_CONFIRM_SCANS
        )

        required_lidar_indices = sorted({
            idx
            for flower_cfg in detector.flowers.values()
            for idx in flower_cfg["angle_indices"]
        })
        
        if testing_mode:
            print("\n[READY] TESTING MODE - Awaiting user input for event simulation...")
            print("Press Ctrl+C to stop.\n")
            print("="*60)
            print("Testing Mode Instructions:")
            print("  - Press ENTER to simulate an event trigger")
            print("  - Each trigger will send images and (if enabled) LiDAR data")
            print("  - Press Ctrl+C to exit")
            print("="*60 + "\n")
        else:
            print("\n[READY] All systems operational. Processing LiDAR data...")
            print("Press Ctrl+C to stop.\n")
            print("="*60)
            print("Communication Pipeline:")
            if lidar_data_client_enabled:
                print("  1. LiDAR trigger -> Event ID generated")
                print("  2. Send images (1050) to image client")
                print("  3. Image client responds (2050) -> forwarded to LiDAR client")
                print("  4. LiDAR client waits for 2050, then sends (2025)")
                print("  5. LiDAR response (2025) -> forwarded to image client")
            else:
                print("  1. LiDAR trigger -> Event ID generated")
                print("  2. Send images (1050) to image client")
                print("  3. LiDAR data client disabled - no LiDAR data transmission")
            print("="*60 + "\n")
        
        # 5. Main processing loop
        scan_count = 0
        start_time = time.time()
        object_count = 0
        
        if testing_mode:
            # Testing mode: wait for user input to simulate events
            while running:
                try:
                    # Wait for user input (non-blocking check)
                    user_input = input("[TEST] Press ENTER to simulate event, or type 'quit' to exit: \n")
                    
                    if user_input.lower() == 'quit':
                        running = False
                        break
                    
                    # Simulate event triggers for testing
                    object_count += 1
                    current_time = time.time()
                    
                    # Simulate event start
                    event_start = {
                        "type": "start",
                        "flower_id": "flower_1",
                        "start_time": current_time,
                        "angles": [68, 69, 70, 71]
                    }
                    on_event_start(event_start, object_count, image_server)
                    
                    # Simulate event end
                    event_end = {
                        "type": "end",
                        "event_type": "flower_visit",
                        "flower_id": "flower_1",
                        "start_time": current_time,
                        "end_time": current_time + 2.0,
                        "num_scans": 16,
                        "angles": [68, 69, 70, 71],
                        "distance_series": [[0.25] * 4 for _ in range(16)]
                    }
                    on_event_end(event_end, lidar_data_server)
                    print()
                    
                except KeyboardInterrupt:
                    running = False
                    break
        else:
            # Normal mode: process LiDAR scans with event detection
            while running:
                # Get next LiDAR scan
                scan_data = lidar.get_scan(timeout=1.0, required_indices=required_lidar_indices)
                
                if scan_data is None:
                    # No scan received, check watchdog
                    current_time = time.time()
                    if not watchdog_check(current_time):
                        print("[WATCHDOG] Attempting to reconnect to LiDAR...")
                        lidar.disconnect()
                        time.sleep(1)
                        if not lidar.connect():
                            print("[ERROR] Failed to reconnect. Exiting.")
                            break
                        last_scan_time = None
                    continue
                
                # Update watchdog timer
                last_scan_time = scan_data["timestamp"]
                scan_count += 1
                
                # Process scan through event detector
                distances = scan_data["ranges"]
                scan_time = scan_data["timestamp"]
                triggered_events = detector.detect_events(distances, scan_time)
                
                # Handle triggered events
                for event in triggered_events:
                    if event["type"] == "start":
                        object_count += 1
                        on_event_start(event, object_count, image_server)
                    elif event["type"] == "end":
                        on_event_end(event, lidar_data_server)
                
                # Print status every 100 scans
                if scan_count % 100 == 0:
                    elapsed = time.time() - start_time
                    print(f"[STATUS] Scans: {scan_count} | Events triggered: {object_count} "
                          f"| Elapsed: {elapsed:.1f}s")
        
        # Shutdown
        print("\n[SHUTDOWN] Main loop stopped")
        elapsed = time.time() - start_time
        
        if testing_mode:
            print(f"\nFinal Statistics (Testing Mode):")
            print(f"  Total events triggered: {object_count}")
            print(f"  Runtime: {elapsed:.2f} seconds")
        else:
            print(f"\nFinal Statistics:")
            print(f"  Total scans processed: {scan_count}")
            print(f"  Total events triggered: {object_count}")
            print(f"  Runtime: {elapsed:.2f} seconds")
        
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up all connections
        print("\n[CLEANUP] Closing connections...")
        
        if lidar and not testing_mode:
            lidar.disconnect()
        elif testing_mode:
            print("[CLEANUP] Testing mode - no LiDAR connection to close")
        
        if image_server:
            image_server.stop_server()
        
        if lidar_data_server:
            lidar_data_server.stop_server()
        
        print("[SHUTDOWN] Complete")


if __name__ == "__main__":
    main()
