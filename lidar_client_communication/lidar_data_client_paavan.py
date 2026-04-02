""" SICKSense Agripollinate LiDAR Data Client Version 2.1 
    Created by: Josiah Faircloth  
    Updated by: Paavan Bagla
    Last Updated: 01/28/2026

    Compatible with Master Main Version 2.0
    
    Receives LiDAR scan data files using packet-based protocol.
    Waits for image client response before sending acknowledgment.
    Immediately generates and sends heatmap response.
    Implements bidirectional communication with cross-client message coordination.
"""

import socket
import os
import sys
import json
import struct
from datetime import datetime

# ============================================================
# PATH CONFIGURATION
# ============================================================
# Adds the parent directory to the search path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Add the lidar_ML directory specifically so its internal imports (like feature_extractor) work
sys.path.append(os.path.join(parent_dir, 'lidar_ML'))

from communication_protocol import (
    Packet,
    PacketHeader,
    PACKET_ID_LIDAR_OUTGOING,
    PACKET_ID_IMAGE_RESPONSE,
    PACKET_ID_LIDAR_RESPONSE,
)
from heatmap.heatmap_generator import generate_heatmap_png


# ============================================================
# RECEIVE COMPLETE PACKET FROM BUFFER
# ============================================================
def receive_packet(receive_buffer: bytes):
    """
    Receive packet-based LiDAR data from server.
    
    Returns:
        (packet, remaining_buffer) - Packet object and remaining data, or (None, buffer) if incomplete
    """

    try:
        if len(receive_buffer) == 0:
            return None, receive_buffer

        # Get expected packet size
        packet_size = Packet.get_packet_size(receive_buffer)

        if packet_size is None:
            # Need more data - buffer is incomplete but potentially valid so far
            return None, receive_buffer

        # Check if we have enough data for the complete packet
        if len(receive_buffer) < packet_size:
            # Need more data - we know the size but don't have all bytes yet
            print(f"[DEBUG] Waiting for complete packet: have {len(receive_buffer)}/{packet_size} bytes")
            return None, receive_buffer

        # Extract packet (we now have enough data)
        packet_data = receive_buffer[:packet_size]
        remaining_buffer = receive_buffer[packet_size:]

        # print(f"[DEBUG] Deserializing complete packet of {packet_size} bytes")

        packet = Packet.deserialize(packet_data)

        if not packet:
            print(f"[ERROR] Failed to deserialize packet of size {packet_size}")
            print(f"[ERROR] First 100 bytes (hex): {packet_data[:100].hex()}")
            # Discard this corrupted packet
            print(f"[ERROR] Discarding {len(packet_data)} bytes of corrupted data")
            return None, remaining_buffer

        return packet, remaining_buffer

    except Exception as e:
        print(f"Error receiving packet: {e}")
        import traceback
        traceback.print_exc()
        return None, receive_buffer

# ============================================================
# HANDLE 1025 LIDAR PACKET
# ============================================================
def handle_lidar_packet(packet: Packet, download_dir="lidar_downloads"):
    """
    Handle received LiDAR packet (1025).
    Save LiDAR JSONL payload to disk and waits for image client response (2050).
    Once received, sends LiDAR response packet (2025).

    Returns:
        Tuple of (file_path, flower_id) where 
        - file_path is the saved JSONL file path and 
        - flower_id is extracted from the JSONL (or "unknown" if not found).
    """

    try:
        # Create download directory
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        # Generate filename and save LiDAR data
        timestamp = datetime.now().strftime("%m-%d-%Y_%H.%M.%S.%f")[:-3]
        filename = f"event_data_{packet.header.event_id}_{timestamp}.jsonl"
        file_path = os.path.join(download_dir, filename)

        # Save JSONL payload
        with open(file_path, "wb") as f:
            f.write(packet.payload)

        # ----------------------------------------------------
        # Extract flower_id from JSONL
        # ----------------------------------------------------
        flower_id = "unknown"

        try:
            with open(file_path, "r") as f:
                first_line = f.readline().strip()
                if first_line:
                    data = json.loads(first_line)
                    flower_id = data.get("flower_id", "unknown")
        except Exception as e:
            print(f"[LIDAR CLIENT] Failed to extract flower_id: {e}")

        # ----------------------------------------------------
        # Logging
        # ----------------------------------------------------    
        print("=" * 90)
        print(f"[LIDAR CLIENT] Event ID: {packet.header.event_id}")
        print(f"[LIDAR CLIENT] Flower ID: {flower_id}")
        print(f"[LIDAR CLIENT] Received and Saved Scan data || File: {file_path}")
        # print(f"[LIDAR CLIENT] Payload size: {len(packet.payload)} bytes")
        print(f"[LIDAR CLIENT] Waiting for image client response (2050)...")

        # return packet.header.event_id, file_path
        return file_path, flower_id

    except Exception as e:
        print(f"Error handling LiDAR packet: {e}")
        return None, None

# ============================================================
# HANDLE IMAGE RESPONSE (2050)
# ============================================================
def handle_image_response_packet(packet: Packet):
    """
    Handle forwarded image response packet (2050) from image client.
    This packet was routed through the master server.
    
    Indicates that image client received its burst and acknowledged it.
    LiDAR client can now send its response.
    
    Returns:
        event_id of the response
    """
    print(f"[LIDAR-IMAGE CLIENT] Received image response (2050) from image client")
    # print(f"[LIDAR-IMAGE CLIENT] Event ID: {packet.header.event_id}")
    try:
        payload_str = packet.payload.decode("utf-8")
        lines = payload_str.strip().split("\n")

        results = []

        for line in lines:
            data = json.loads(line)

            detections = data.get("detections", [])
            total = data.get("total_detections", 0)

            # check if any pollinator detected
            pollinator_detected = False
            max_conf = 0.0

            for det in detections:
                class_name = det.get("class_name", "").lower()
                confidence = det.get("confidence", 0)
                
                if class_name == "bee":
                    pollinator_detected = True
                    if confidence > max_conf:
                        max_conf = confidence

            print(f"[LIDAR-IMAGE CLIENT] Detections: {total} || Pollinator: {pollinator_detected} || Max Conf: {max_conf:.3f}")

            results.append({
                "pollinator": pollinator_detected,
                "count": total,
                "confidence": max_conf
            })

        return packet.header.event_id, results

    except Exception as e:
        print(f"[LIDAR-IMAGE CLIENT ERROR] Failed to parse image response: {e}")
        return packet.header.event_id, None

# ============================================================
# CREATE 2025 RESPONSE PACKET
# ============================================================
def create_lidar_response_packet(event_id: str, json_file_path: str, camera_data=None, flower_id=None):
    """
    Generate heatmap PNG and package into response packet.
    """

    print("[LIDAR CLIENT] Generating heatmap...")

    # png_bytes = generate_heatmap_png(json_file_path, camera_data)

    # if png_bytes is None:
    #     print("[LIDAR CLIENT] No bees detected. Sending empty payload.")
    #     png_bytes = b""

    # header = PacketHeader(event_id, PACKET_ID_LIDAR_RESPONSE) # Response packet ID for LiDAR client
    # packet = Packet(header, png_bytes) # Payload is the PNG image bytes

    # print(f"[LIDAR CLIENT] Heatmap ready ({len(png_bytes)} bytes)")

    result = generate_heatmap_png(json_file_path, camera_data, flower_id)
    if result is None:
        print("[LIDAR CLIENT] No bees detected. Sending empty payload.")
        png_bytes = b""
        detection_json = json.dumps({"pollinator_detected": False}).encode("utf-8")
    else:
        png_bytes, detection_json = result
    
    # Save the detection JSON locally
    detection_dir = "detection_results"
    os.makedirs(detection_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%m-%d-%Y_%H.%M.%S.%f")[:-3]
    detection_path = os.path.join(detection_dir, f"detection_{event_id}_{timestamp}.json")
    with open(detection_path, "wb") as f:
        f.write(detection_json)
    print(f"[LIDAR CLIENT] Detection JSON saved: {detection_path}")

    # Payload = [4-byte PNG length][PNG bytes][JSON bytes]
    png_len = struct.pack(">I", len(png_bytes))   # 4-byte big-endian unsigned int
    combined_payload = png_len + png_bytes + detection_json

    header = PacketHeader(event_id, PACKET_ID_LIDAR_RESPONSE)
    packet = Packet(header, combined_payload)
    print(f"[LIDAR CLIENT] Heatmap ready ({len(png_bytes)} bytes PNG + {len(detection_json)} bytes JSON)")
    
    print("[LIDAR CLIENT] Sending 2025 response to server")

    return packet

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    # Server configuration
    HOST = "10.250.76.217" # Rasp Pi : 192.168.1.74 (Home WIFI) : 10.250.76.217 (TAMU IoT)
    PORT = 12346 # Different port from image client

    download_dir = "lidar_downloads"
    camera_results = {}   # event_id -> camera info
    pending_files = {}      # event_id -> lidar file path

    try:
        # Create TCP socket and connect to server
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((HOST, PORT))\
        
        print(f"Connected to LiDAR data server at {HOST}:{PORT}")
        print("Waiting for LiDAR scan data files... (Ctrl+C to quit)\n")

        receive_buffer = b""

        # =====================================================
        # HELPER: process event if both parts exist
        # =====================================================
        def try_process_event(event_id):
            if event_id in pending_files and event_id in camera_results:
                
                event_data = pending_files[event_id]
                json_file_path = event_data["file_path"]
                flower_id = event_data["flower_id"]
                cam_data = camera_results[event_id]

                print(f"[EVENT INFO] Event {event_id} triggered at Flower: {flower_id}")
                response_packet = create_lidar_response_packet(
                    event_id,
                    json_file_path,
                    cam_data,
                    flower_id
                )

                client_socket.sendall(response_packet.serialize())

                print(f"[LIDAR CLIENT] Sent 2025 response for event {event_id}")
                print("=" * 90 + "\n")

                # cleanup
                pending_files.pop(event_id, None)
                camera_results.pop(event_id, None)

        # =====================================================
        # MAIN RECEIVE LOOP
        # =====================================================
        while True:
            data = client_socket.recv(4096)
            if not data:
                print("Server closed connection")
                break
            receive_buffer += data

            # Process all complete packets in buffer
            while True:
                packet, receive_buffer = receive_packet(receive_buffer)
                if packet is None:
                    break # Need more data

                packet_id = packet.header.packet_id
                event_id = packet.header.event_id

                # --------------------------------------------------
                # LIDAR PACKET (1025) FROM SERVER
                # --------------------------------------------------
                if packet_id == PACKET_ID_LIDAR_OUTGOING:
                    
                    file_path, flower_id = handle_lidar_packet(packet, download_dir)

                    # guard against bad save
                    if file_path is None:
                        continue
                    
                    pending_files[event_id] = {
                        "file_path": file_path,
                        "flower_id": flower_id
                    }
                    
                    # try processing (handles IMAGE → LIDAR case)
                    try_process_event(event_id)

                # --------------------------------------------------
                # 2050 IMAGE RESPONSE
                # --------------------------------------------------
                elif packet_id == PACKET_ID_IMAGE_RESPONSE:

                    event_id, cam_result = handle_image_response_packet(packet)

                    # guard against bad save
                    if cam_result is not None:
                        camera_results[event_id] = cam_result

                    # try processing (handles LIDAR → IMAGE case)
                    try_process_event(event_id)

                else:
                    print(f"[LIDAR CLIENT] Unknown packet ID: {packet_id}")

    except ConnectionRefusedError:
        print(f"Could not connect to server at {HOST}:{PORT}")
        print("Make sure the server is running.")
        
    except Exception as e:
        print(f"Client error: {e}")

    finally:
        client_socket.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
