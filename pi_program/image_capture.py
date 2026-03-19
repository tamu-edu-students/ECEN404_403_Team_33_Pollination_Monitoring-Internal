""" SICKSense Agripollinate Image Capture Module Version 2.0
    Created by:    Josiah Faircloth
    date:    01/28/2026

    Handles image capture from USB camera and bidirectional TCP communication.
    Implements custom communication protocol with packet headers and event tracking.
    Supports message routing between image and LiDAR clients through master server.
"""

import socket
import select
import os
import subprocess
from datetime import datetime
import sys
import threading
import time
# Adds the parent directory to the search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from communication_protocol import Packet, PacketHeader, PACKET_ID_IMAGE_OUTGOING, PACKET_ID_IMAGE_RESPONSE, PACKET_ID_LIDAR_RESPONSE


class ImageServer:
    """
    Manages TCP connection to image client and handles burst image capture/transmission.
    Implements bidirectional communication with packet-based protocol.
    Routes cross-client messages between image and LiDAR clients.
    """
    
    def __init__(self, host='0.0.0.0', port=12345, save_dir="/home/josiah", resolution="640x480", lidar_server=None):
        self.host = host
        self.port = port
        self.save_dir = save_dir
        self.resolution = resolution
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        self.connected = False
        self.running = False
        self.lidar_server = lidar_server  # Reference to LiDAR server for message routing
        
        # Bidirectional communication
        self.receive_thread = None
        self.receive_buffer = b''
        self.pending_responses = {}  # {event_id: packet_data}
        self.response_lock = threading.Lock()
        
        # Create save directory if it doesn't exist
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
    
    def start_server(self, accept_timeout=1.0):
        """Start server and wait for client connection.

        Uses short accept timeouts so Ctrl+C/shutdown can stop cleanly
        even before a client finishes connecting.
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(accept_timeout)
            self.running = True
            print(f"Image server listening on {self.host}:{self.port}")
            print("Waiting for client connection...")
            
            # Accept client connection in an interruptible loop.
            while self.running and not self.connected:
                try:
                    self.client_socket, self.client_address = self.server_socket.accept()
                    self.connected = True
                except socket.timeout:
                    continue

            if not self.connected:
                print("Image server stopped before client connected")
                return False

            self.connected = True
            print(f"Image client connected: {self.client_address}")
            
            # Start receive thread for bidirectional communication
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            return True
            
        except Exception as e:
            print(f"Failed to start image server: {e}")
            self.running = False
            return False
    
    def stop_server(self):
        """Stop server and close connections"""
        self.running = False
        
        if self.client_socket:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR)
                self.client_socket.close()
            except:
                pass
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        self.connected = False
        print("Image server stopped")
    
    def _receive_loop(self):
        """
        Continuously receive and process packets from image client.
        Handles packet parsing and cross-client message routing.
        """
        while self.running and self.connected:
            try:
                readable, _, _ = select.select([self.client_socket], [], [], 0.5)
                if not readable:
                    continue

                data = self.client_socket.recv(4096)
                
                if not data:
                    print("Image client disconnected")
                    self.connected = False
                    break
                
                self.receive_buffer += data
                
                # Try to extract complete packets
                while len(self.receive_buffer) > 0:
                    packet_size = Packet.get_packet_size(self.receive_buffer)
                    
                    if packet_size is None:
                        break  # Not enough data for a complete packet
                    
                    packet_data = self.receive_buffer[:packet_size]
                    self.receive_buffer = self.receive_buffer[packet_size:]
                    
                    packet = Packet.deserialize(packet_data)
                    if packet:
                        self._handle_received_packet(packet)
                
            except Exception as e:
                if self.running:
                    print(f"Error in image server receive loop: {e}")
                break
    
    def _handle_received_packet(self, packet: Packet):
        """
        Process received packet from image client.
        
        Packet ID 2050: Image client response - route to LiDAR client
        """
        event_id = packet.header.event_id
        packet_id = packet.header.packet_id
        
        if packet_id == PACKET_ID_IMAGE_RESPONSE:  # 2050
            print(f"[IMAGE SERVER] Received response (2050) from image client, event_id: {event_id}")
            
            # Store for later retrieval or immediate routing
            with self.response_lock:
                self.pending_responses[event_id] = packet
            
            # Forward to LiDAR client if server reference available
            if self.lidar_server and self.lidar_server.connected:
                # Forward with same header but no modification
                self._forward_to_lidar_client(packet)
        else:
            print(f"[IMAGE SERVER] Received unexpected packet (ID: {packet_id}) from image client")
    
    def _forward_to_lidar_client(self, packet: Packet):
        """Forward packet to LiDAR client (cross-client routing)"""
        try:
            if self.lidar_server and self.lidar_server.connected:
                serialized = packet.serialize()
                self.lidar_server.client_socket.sendall(serialized)
                print(f"[IMAGE SERVER] Forwarded packet (ID: {packet.header.packet_id}) to LiDAR client, event_id: {packet.header.event_id}")
        except Exception as e:
            print(f"Error forwarding to LiDAR client: {e}")
    
    def capture_image(self):
        """Capture an image from USB camera using fswebcam"""
        try:
            # Create unique filename based on timestamp
            timestamp = datetime.now().strftime("%m-%d-%Y_%H.%M.%S.%f")[:-3]
            image_path = os.path.join(self.save_dir, f"captured_{timestamp}.jpg")
            
            # Capture image via USB camera
            subprocess.run(
                ["fswebcam", "-r", self.resolution, image_path], 
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"Image captured: {image_path}")
            return image_path
            
        except subprocess.CalledProcessError:
            print("Failed to capture image")
            return None
    
    
    def send_images_with_packet(self, event_id: str, image_paths: list) -> bool:
        """
        Send images with packet-based protocol (new method).
        
        Args:
            event_id: Event ID for this transmission
            image_paths: List of image file paths to send
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connected:
            print("Cannot send images: No client connected")
            return False
        
        try:
            print(f"[IMAGE SERVER] Sending {len(image_paths)} images with event_id: {event_id}")
            
            for image_path in image_paths:
                if not os.path.exists(image_path):
                    print(f"Image file not found: {image_path}")
                    continue
                
                # Create packet with image data
                with open(image_path, 'rb') as f:
                    image_data = f.read()
                
                header = PacketHeader(event_id, PACKET_ID_IMAGE_OUTGOING)
                packet = Packet(header, image_data)
                serialized = packet.serialize()
                
                # Send packet with debug info
                '''
                print(f"[IMAGE SERVER] Packet structure:")
                print(f"  - Event ID: {event_id}")
                print(f"  - Packet ID: {PACKET_ID_IMAGE_OUTGOING}")
                print(f"  - Image size: {len(image_data)} bytes")
                print(f"  - Serialized size: {len(serialized)} bytes")
                '''
                print(f"[IMAGE SERVER] Sending packet...")
                self.client_socket.sendall(serialized)
                print(f"[IMAGE SERVER] Sent image packet: {os.path.basename(image_path)}, event_id: {event_id}")
                
            
            return True

        except TimeoutError:
            print(f"Error sending image packet: timed out")
            return False
            
        except Exception as e:
            print(f"Error sending image packet: {e}")
            import traceback
            traceback.print_exc()
            self.connected = False
            return False
    
    def __enter__(self):
        """Context manager support"""
        self.start_server()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.stop_server()
