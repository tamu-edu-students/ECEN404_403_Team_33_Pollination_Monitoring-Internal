""" SICKSense Agripollinate LiDAR Parser Module Version 1.0
    Created by:    Josiah Faircloth 
    date:    11/30/2025

    Handles real-time LiDAR data parsing from SICK TiM561 LiDAR scanner.
    Extracted from LiDAR Logger Version 0.1 for integration into master program.
"""

import socket
import time

# LiDAR Communication Commands
CMD_START = b'\x02sEN LMDscandata 1\x03'  # Start streaming command
CMD_STOP = b'\x02sEN LMDscandata 0\x03'   # Stop streaming command


class LidarConnection:
    """Manages TCP connection and data streaming from SICK TiM561 LiDAR"""
    
    def __init__(self, host="192.168.137.2", port=2112):
        self.host = host
        self.port = port
        self.socket = None
        self.buffer = ""
        self.connected = False
    
    def connect(self, timeout=10.0):
        """Establish connection to LiDAR and start data streaming"""
        try:
            print(f"Attempting to connect to LiDAR at {self.host}:{self.port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)  # Set connection timeout
            self.socket.connect((self.host, self.port))
            self.socket.sendall(CMD_START)
            self.connected = True
            print(f"Connected to LiDAR at {self.host}:{self.port}")
            return True
        except socket.timeout:
            print(f"Connection timed out after {timeout} seconds")
            print(f"Check if LiDAR is powered on and reachable at {self.host}")
            self.connected = False
            return False
        except ConnectionRefusedError:
            print(f"Connection refused by {self.host}:{self.port}")
            print("Check if the LiDAR scanner is running and the port is correct")
            self.connected = False
            return False
        except Exception as e:
            print(f"Failed to connect to LiDAR: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Stop streaming and close connection"""
        if self.socket and self.connected:
            try:
                self.socket.sendall(CMD_STOP)
                self.socket.close()
                print("LiDAR connection closed")
            except Exception as e:
                print(f"Error disconnecting from LiDAR: {e}")
            finally:
                self.connected = False
    
    def parse_scan(self, telegram, required_indices=None):
        """Extract distance measurements from an LMDscandata telegram.

        If required_indices is provided, only those DIST1 indices are parsed and
        returned as a dictionary {index: distance_meters}. Otherwise, all
        distances are parsed and returned as a list.
        """
        parts = telegram.strip().split(' ')
        if 'DIST1' not in parts:
            return None
        
        try:
            num_index = parts.index('DIST1') + 5
            num_values = int(parts[num_index], 16)

            values_start = num_index + 1
            values_end = values_start + num_values
            dist_hex_values = parts[values_start:values_end]

            if required_indices is not None:
                selected_distances = {}
                for index in required_indices:
                    if index < 0 or index >= num_values:
                        return None
                    selected_distances[index] = int(dist_hex_values[index], 16) / 1000.0
                return selected_distances

            distances = [int(v, 16) / 1000.0 for v in dist_hex_values]
            return distances
        except Exception:
            return None
    
    def get_scan(self, timeout=1.0, required_indices=None):
        """
        Read and return the next complete scan from the LiDAR.
        Returns: dict with 'timestamp', 'num_points', 'ranges' or None if error/timeout

        - If required_indices is None, 'ranges' is a full list of distances.
        - If required_indices is provided, 'ranges' is a dict mapping index->distance.
        """
        if not self.connected:
            return None
        
        start_time = time.time()
        
        try:
            while time.time() - start_time < timeout:
                # Receive data with short timeout
                self.socket.settimeout(0.1)
                try:
                    data = self.socket.recv(4096).decode(errors='ignore')
                    self.buffer += data
                except socket.timeout:
                    continue
                
                # Check if we have a complete telegram
                if '\x03' in self.buffer:
                    telegram, self.buffer = self.buffer.split('\x03', 1)
                    telegram = telegram.replace('\x02', '').strip()
                    distances = self.parse_scan(telegram, required_indices=required_indices)
                    
                    if distances:
                        return {
                            "timestamp": time.time(),
                            "num_points": len(distances),
                            "ranges": distances
                        }
            
            return None  # Timeout reached
            
        except Exception as e:
            print(f"Error reading scan: {e}")
            return None
    
    def __enter__(self):
        """Context manager support"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.disconnect()
