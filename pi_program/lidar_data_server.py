""" SICKSense Agripollinate LiDAR Data Server Module Version 2.0
    Created by:    Josiah Faircloth
    date:    01/28/2026

    Handles transmission and reception of LiDAR scan data via TCP.
    Implements custom communication protocol with packet headers and event tracking.
    Supports message routing between LiDAR and image clients through master server.
"""

import socket
import os
import json
import threading
import time
from datetime import datetime
from communication_protocol import Packet, PacketHeader, PACKET_ID_LIDAR_OUTGOING, PACKET_ID_LIDAR_RESPONSE, PACKET_ID_IMAGE_RESPONSE


class LidarDataServer:
    """
    Manages TCP connection to LiDAR data client and handles scan data transmission.
    Implements bidirectional communication with packet-based protocol.
    Routes cross-client messages between LiDAR and image clients.
    """
    
    def __init__(self, host='0.0.0.0', port=12346, save_dir="/home/josiah/pi_program/lidar_data", image_server=None):
        self.host = host
        self.port = port
        self.save_dir = 'lidar_downloads'
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        self.connected = False
        self.running = False
        self.image_server = image_server  # Reference to image server for message routing
        
        self.scan_buffer = []  # Buffer to store recent scans
        self.buffer_size = 20  # Number of scans to keep in buffer
        
        # Bidirectional communication
        self.receive_thread = None
        self.receive_buffer = b''
        self.pending_responses = {}  # {event_id: packet_data}
        self.response_lock = threading.Lock()
        
        # Create save directory if it doesn't exist
        try:
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)
        except OSError as e:
            print(f"[LIDAR SERVER] Warning: could not create save directory '{self.save_dir}': {e}")
    
    def start_server(self, timeout=10.0):
        """Start server and wait for LiDAR data client connection 
           Returns True if client connected, False otherwise"""

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.settimeout(timeout)  # Set connection timeout
            self.server_socket.listen(1)
            self.running = True
            print(f"LiDAR data server listening on {self.host}:{self.port}")
            print("Waiting for LiDAR data client connection...")
            
            # Accept client connection
            self.client_socket, self.client_address = self.server_socket.accept()
            self.connected = True
            print(f"LiDAR data client connected: {self.client_address}")
            
            # Start receive thread for bidirectional communication
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            return True  
        
        except socket.timeout:
            print(f"Connection timed out after {timeout} seconds")
            print(f"Check if LiDAR Data client is reachable at {self.host}")
            self.connected = False
            return False
        except ConnectionRefusedError:
            print(f"Connection refused by {self.host}:{self.port}")
            print("Check if the LiDAR Data client is running and the port is correct")
            self.connected = False
            return False
        except Exception as e:
            print(f"Failed to start LiDAR data server: {e}")
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
        print("LiDAR data server stopped")
    
    
    def _receive_loop(self):
        """
        Continuously receive and process packets from LiDAR client.
        Handles packet parsing and cross-client message routing.
        """
        while self.running and self.connected:
            try:
                data = self.client_socket.recv(4096)
                
                if not data:
                    print("LiDAR client disconnected")
                    self.connected = False

                    self._attempt_reconnect()  # Attempt to reconnect if client disconnects

                    if not self.running:
                        break  # Server was stopped, exit loop cleanly
                    else:
                        continue  # Reconnected, resume receive loop
                
                self.receive_buffer += data
                
                # Try to extract complete packets
                while True:
                    packet_size = Packet.get_packet_size(self.receive_buffer)
                    
                    if packet_size is None:
                        break  # Not enough data for a complete packet
                    
                    if len(self.receive_buffer) < packet_size:
                        break

                    packet_data = self.receive_buffer[:packet_size]
                    self.receive_buffer = self.receive_buffer[packet_size:]
                    
                    packet = Packet.deserialize(packet_data)
                    if packet:
                        self._handle_received_packet(packet)
            
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                if self.running:
                    print(f"[LIDAR SERVER] Connection error in receive loop: {e}")
                self.connected = False
                self._attempt_reconnect()
                if not self.connected:
                    break
                continue

            except Exception as e:
                if self.running:
                    print(f"Error in LiDAR server receive loop: {e}")
                break
    
    def _attempt_reconnect(self):
        """Attempt to reconnect to LiDAR data client."""
        print("[LIDAR SERVER] Attempting to reconnect to LiDAR data client...")
        while self.running and not self.connected:
            try:
                self.server_socket.settimeout(5.0)
                self.client_socket, self.client_address = self.server_socket.accept()
                self.client_socket.settimeout(None)
                self.connected = True
                self.receive_buffer = b''
                print(f"[LIDAR SERVER] LiDAR data client reconnected: {self.client_address}")
            except socket.timeout:
                print("[LIDAR SERVER] Reconnect attempt timed out, retrying...")
                continue
            except Exception as e:
                if self.running:
                    print(f"[LIDAR SERVER] Reconnect error: {e}, retrying...")
                time.sleep(1.0)
                continue
            
    
    def _handle_received_packet(self, packet: Packet):
        """
        Process received packet from LiDAR client.
        
        Packet ID 2025: LiDAR client response - route to image client
        Packet ID 2050: Image client response (forwarded) - should not receive directly
        """
        print(f'Handling received packet with ID: {packet.header.packet_id}')

        event_id = packet.header.event_id
        packet_id = packet.header.packet_id
        
        if packet_id == PACKET_ID_LIDAR_RESPONSE:  # 2025
            print(f"[LIDAR SERVER] Received response (2025) from LiDAR client, event_id: {event_id}")
            
            # Store for later retrieval or immediate routing
            with self.response_lock:
                self.pending_responses[event_id] = packet
            
            # Forward to image client if server reference available
            if self.image_server and self.image_server.connected:
                self._forward_to_image_client(packet)
        elif packet_id == PACKET_ID_IMAGE_RESPONSE:  # 2050
            print(f"[LIDAR SERVER] Received image response (2050) forwarded through network, event_id: {event_id}")
        else:
            print(f"[LIDAR SERVER] Received unexpected packet (ID: {packet_id}) from LiDAR client")
    
    def _forward_to_image_client(self, packet: Packet):
        """Forward packet to image client (cross-client routing)"""
        try:
            if self.image_server and self.image_server.connected:
                serialized = packet.serialize()
                self.image_server.client_socket.sendall(serialized)
                print(f"[LIDAR SERVER] Forwarded packet (ID: {packet.header.packet_id}) to image client, event_id: {packet.header.event_id}")

        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[LIDAR SERVER] Error forwarding to image client (connection lost): {e}")
            # Mark image server as disconnected so it can attempt its own reconnect
            if self.image_server:
                self.image_server.connected = False
        except Exception as e:
            print(f"Error forwarding to image client: {e}")

    def save_outgoing_lidar_packet(self, packet: Packet):
        """
        Save outgoing LiDAR event payload locally using the same naming format
        as the LiDAR data client.
        """
        if packet.header.packet_id != PACKET_ID_LIDAR_OUTGOING:
            return None

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

        timestamp = datetime.now().strftime("%m-%d-%Y_%H.%M.%S.%f")[:-3]
        filename = f"event_data_{packet.header.event_id}_{timestamp}.jsonl"
        file_path = os.path.join(self.save_dir, filename)

        with open(file_path, "wb") as file_handle:
            file_handle.write(packet.payload)

        print(f"[LIDAR SERVER] Saved outgoing LiDAR event data: {file_path}")
        return file_path

    def send_lidar_packet(self, packet: Packet):
        """
        Send a LiDAR packet to the connected LiDAR data client.
        Also saves packet payload locally for outgoing LiDAR event packets.
        """
        if not self.connected or not self.client_socket:
            raise ConnectionError("LiDAR data client is not connected")

        try:
            self.save_outgoing_lidar_packet(packet)
        except Exception as e:
            print(f"[LIDAR SERVER] Warning: local save failed, continuing send: {e}")
        self.client_socket.sendall(packet.serialize())
    
    
    def __enter__(self):
        """Context manager support"""
        self.start_server()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.stop_server()
