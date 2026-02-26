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
from datetime import datetime

# Adds the parent directory to the search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from communication_protocol import (
    Packet,
    PacketHeader,
    PACKET_ID_LIDAR_OUTGOING,
    PACKET_ID_IMAGE_RESPONSE,
    PACKET_ID_LIDAR_RESPONSE,
)
from Heatmap.heatmap_generator import generate_heatmap_png

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

        print(f"[DEBUG] Deserializing complete packet of {packet_size} bytes")

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
        Tuple of (event_id, packet) for tracking
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

        print(f"[LIDAR CLIENT] Received and Saved Scan data")
        print(f"[LIDAR CLIENT] Event ID: {packet.header.event_id}")
        print(f"[LIDAR CLIENT] File: {file_path}")
        print(f"[LIDAR CLIENT] Payload size: {len(packet.payload)} bytes")
        print(f"[LIDAR CLIENT] Waiting for image client response (2050)...")

        # return packet.header.event_id, file_path
        return file_path

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
    print(f"[LIDAR CLIENT] Received image response (2050) from image client")
    print(f"[LIDAR CLIENT] Event ID: {packet.header.event_id}")
    print(f"[LIDAR CLIENT] Image payload size: {len(packet.payload)} bytes")
    
    return packet.header.event_id

# ============================================================
# CREATE 2025 RESPONSE PACKET
# ============================================================
def create_lidar_response_packet(event_id: str, json_file_path: str):
    """
    Generate heatmap PNG and package into response packet.
    """

    print("[LIDAR CLIENT] Generating heatmap...")

    png_bytes = generate_heatmap_png(json_file_path)

    if png_bytes is None:
        print("[LIDAR CLIENT] No bees detected. Sending empty payload.")
        png_bytes = b""

    header = PacketHeader(event_id, PACKET_ID_LIDAR_RESPONSE) # Response packet ID for LiDAR client
    packet = Packet(header, png_bytes) # Payload is the PNG image bytes

    print(f"[LIDAR CLIENT] Heatmap ready ({len(png_bytes)} bytes)")
    print('Heatmap generated and saved as pollinator_map.png')
    print("[LIDAR CLIENT] Sending 2025 response to server\n")

    return packet

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    # Server configuration
    HOST = "10.250.76.217" # Rasp Pi : 192.168.1.74 (Home WIFI) : 10.250.76.217 (TAMU IoT)
    PORT = 12346 # Different port from image client
    download_dir = "lidar_downloads"

    try:
        # Create TCP socket and connect to server
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((HOST, PORT))
        print(f"Connected to LiDAR data server at {HOST}:{PORT}")
        print("Waiting for LiDAR scan data files... (Ctrl+C to quit)\n")

        receive_buffer = b""
        pending_files = {}  # event_id -> json_file_path

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
                # 1025 FROM SERVER
                # --------------------------------------------------
                if packet_id == PACKET_ID_LIDAR_OUTGOING:
                    file_path = handle_lidar_packet(packet, download_dir)
                    pending_files[event_id] = file_path

                # --------------------------------------------------
                # 2050 IMAGE RESPONSE
                # --------------------------------------------------
                elif packet_id == PACKET_ID_IMAGE_RESPONSE:

                    print("[LIDAR CLIENT] Received image response (2050)")
                    print(f"[LIDAR CLIENT] Event ID: {event_id}")

                    if event_id in pending_files:
                        json_file_path = pending_files[event_id]

                        response_packet = create_lidar_response_packet(
                            event_id, json_file_path
                        )

                        # IMPORTANT: always use sendall
                        client_socket.sendall(response_packet.serialize())
                        print(f"[LIDAR CLIENT] Sent 2025 response for event {event_id}\n")

                        del pending_files[event_id]

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
