""" SICKSense Agripollinate LiDAR Parser Module Version 1.0
    Created by:    Josiah Faircloth 
    date:    11/30/2025

    Handles real-time LiDAR data parsing from SICK TiM561 LiDAR scanner.
    Extracted from LiDAR Logger Version 0.1 for integration into master program.
"""

import socket
import time
import json
from datetime import datetime
import statistics
import os

# LiDAR Communication Commands
CMD_START = b'\x02sEN LMDscandata 1\x03'  # Start streaming command
CMD_STOP = b'\x02sEN LMDscandata 0\x03'   # Stop streaming command

NUM_BASELINE_SCANS = 100
MAX_PLANT_DIST = 0.5  # meters

# Spatial clustering parameters
MIN_BLOCK_SIZE = 3
MAX_BLOCK_SIZE = 25
MAX_DIST_STD = 0.08

# Temporal persistence parameters
ANGLE_TOLERANCE = 5  # degrees, for matching clusters across scans
DIST_TOLERANCE = 0.15
MIN_HITS = 20

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
            # self.socket.sendall(CMD_START)
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
        
    def start(self):
        """Send command to start LiDAR data streaming"""
        if self.connected:
            try:
                self.socket.sendall(CMD_START)
                print("LiDAR streaming started")
            except Exception as e:
                print(f"Error starting LiDAR stream: {e}")
    
    def end(self):
        """Send command to stop LiDAR data streaming"""
        if self.connected:
            try:
                self.socket.sendall(CMD_STOP)
                print("LiDAR streaming stopped")
            except Exception as e:
                print(f"Error stopping LiDAR stream: {e}")
    
    def disconnect(self):
        """Stop streaming and close connection"""
        if self.socket and self.connected:
            try:
                #  self.socket.sendall(CMD_STOP)
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
    
    def extract_clusters_from_scan(self,distances):
        """
        Phase 1: spatial clustering for one scan.
        Groups contiguous indices ONLY if distance is similar and within working range.
        """
        clusters = []
        if not distances:
            return clusters
            
        current_block = [0]
        
        for i in range(1, len(distances)):
            # Check if the next point is physically close to the previous one
            if abs(distances[i] - distances[i - 1]) <= MAX_DIST_STD:
                current_block.append(i)
            else:
                # Process the block we just finished
                self.process_potential_cluster(current_block, distances, clusters)
                current_block = [i]

        # Don't forget the last block in the scan
        self.process_potential_cluster(current_block, distances, clusters)

        return clusters
    
    def process_potential_cluster(self, block, distances, cluster_list):
        """Helper to validate size and distance before adding to the list."""
        if MIN_BLOCK_SIZE <= len(block) <= MAX_BLOCK_SIZE:
            block_dists = [distances[j] for j in block]
            mean_dist = statistics.mean(block_dists)
            
            # WORKING RANGE FILTER:
            # This is the "cleanest place" to drop background vegetation
            if mean_dist <= MAX_PLANT_DIST:
                cluster_list.append({
                    "indices": block,
                    "angle_center": int(statistics.mean(block)),
                    "mean_dist": round(mean_dist, 3)
                })
    
    def setup_flowers(self):
        timestamp = datetime.now().strftime("%m_%d_%Y_%H_%M_%S")
        if not os.path.exists('setup'):
                os.makedirs('setup')
        
        out_file = f"setup/flower_setup_{timestamp}.json"

        scans = []

        # -----------------------------
        # Collect scans
        # -----------------------------
        
        self.socket.sendall(CMD_START)
        
        print("Collecting scans for flower setup.....")

        buffer = ""

        while len(scans) < NUM_BASELINE_SCANS:
            data = self.socket.recv(4096).decode(errors="ignore")
            buffer += data

            while "\x03" in buffer and len(scans) < NUM_BASELINE_SCANS:
                telegram, buffer = buffer.split("\x03", 1)
                telegram = telegram.replace("\x02", "").strip()

                scan = self.parse_scan(telegram)
                if scan:
                    scans.append(scan)

        self.socket.sendall(CMD_STOP)

        print(f"\nCollected {len(scans)} scans\n")

        # -----------------------------
        # Phase 2: temporal clustering
        # -----------------------------
        tracks = []

        for scan in scans:
            clusters = self.extract_clusters_from_scan(scan)

            for c in clusters:
                matched = False

                for track in tracks:
                    if abs(c["angle_center"] - track["angle_center"]) <= ANGLE_TOLERANCE:
                        if abs(c["mean_dist"] - track["mean_dist"]) <= DIST_TOLERANCE:
                            track["hits"] += 1
                            track["all_indices"].append(c["indices"])
                            track["all_dists"].append(c["mean_dist"])
                            matched = True
                            break

                if not matched:
                    tracks.append({
                        "angle_center": c["angle_center"],
                        "mean_dist": c["mean_dist"],
                        "hits": 1,
                        "all_indices": [c["indices"]],
                        "all_dists": [c["mean_dist"]]
                    })

        # -----------------------------
        # Final flower selection
        # -----------------------------
        flower_config = {}
        flower_id = 1

        for track in tracks:
            if track["hits"] < MIN_HITS:
                continue

            merged_indices = sorted(
                set(i for block in track["all_indices"] for i in block)
            )

            mean_dist = statistics.mean(track["all_dists"])

            print(f"Candidate for flower {flower_id}:")
            print(f"Indices {merged_indices}")
            print(f"Distance {mean_dist:.2f} m\n")

            include = input(f"Would you like to include this flower? (y/n):  ")
            if include.lower() == 'y':
                flower_config[f"flower_{flower_id}"] = {
                "angle_indices": merged_indices,
                "background_dist": round(mean_dist, 3)
                }

                flower_id += 1
            
        with open(out_file, "w") as f:
            json.dump(flower_config, f, indent=2)

        print(f"Saved flower configuration to {out_file}")
        return flower_config
    

    def __enter__(self):
        """Context manager support"""
        self.connect()
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.end()
        self.disconnect()
