""" SICKSense Agripollinate Communication Protocol Module Version 1.0
    Created by:    Josiah Faircloth
    date:    01/28/2026

    Defines packet structure and serialization for bidirectional communication
    between master server and client devices. Implements custom protocol with
    event tracking and inter-client message routing.
"""

import json
import struct
from typing import Optional, Tuple


# Packet Identifier Constants
PACKET_ID_LIDAR_OUTGOING = 1025    # Master -> LiDAR client (scan data)
PACKET_ID_IMAGE_OUTGOING = 1050    # Master -> Image client (image data)
PACKET_ID_IMAGE_RESPONSE = 2050    # Image client -> Master (response)
PACKET_ID_LIDAR_RESPONSE = 2025    # LiDAR client -> Master (response)


class PacketHeader:
    """
    Packet header containing event ID and packet identifier.
    
    Header format:
    - Event ID: 6 digits before decimal, 2 after (from time.time())
    - Packet Identifier: 4-digit integer
    - Total: variable length JSON for flexibility
    """
    
    def __init__(self, event_id: str, packet_id: int):
        """
        Initialize packet header.
        
        Args:
            event_id: String formatted as "XXXXXXXX.XX" from time.time() timestamp
            packet_id: Integer packet identifier (1025, 1050, 2025, 2050)
        """
        self.event_id = event_id
        self.packet_id = packet_id
    
    def to_json(self) -> str:
        """Serialize header to JSON string"""
        return json.dumps({
            "event_id": self.event_id,
            "packet_id": self.packet_id
        })
    
    @staticmethod
    def from_json(json_str: str) -> 'PacketHeader':
        """Deserialize header from JSON string"""
        data = json.loads(json_str)
        return PacketHeader(data["event_id"], data["packet_id"])
    
    def __repr__(self):
        return f"Header(event_id={self.event_id}, packet_id={self.packet_id})"


class Packet:
    """
    Complete packet structure with header and payload.
    
    Format:
    [Header Length: 4 bytes][Header: JSON][Payload Length: 4 bytes][Payload: binary]
    """
    
    def __init__(self, header: PacketHeader, payload: bytes = b''):
        """
        Initialize packet.
        
        Args:
            header: PacketHeader object
            payload: Binary payload data
        """
        self.header = header
        self.payload = payload
    
    def serialize(self) -> bytes:
        """Serialize packet to bytes for transmission"""
        header_json = self.header.to_json()
        header_bytes = header_json.encode('utf-8')
        
        # Format: [header_length(4)][header_bytes][payload_length(4)][payload_bytes]
        serialized = struct.pack('>I', len(header_bytes))  # Header length (big-endian)
        serialized += header_bytes
        serialized += struct.pack('>I', len(self.payload))  # Payload length (big-endian)
        serialized += self.payload
        
        return serialized
    
    @staticmethod
    def deserialize(data: bytes) -> Optional['Packet']:
        """
        Deserialize packet from bytes.
        
        Returns:
            Packet object if successful, None if data is incomplete
        """
        try:
            if len(data) < 8:  # Need at least header_length + payload_length
                return None
            
            # Read header length
            header_length = struct.unpack('>I', data[0:4])[0]
            
            if len(data) < 4 + header_length + 4:  # Not enough data for complete header and payload length
                return None
            
            # Read header
            header_bytes = data[4:4+header_length]
            header_json = header_bytes.decode('utf-8')
            header = PacketHeader.from_json(header_json)
            
            # Read payload length
            payload_offset = 4 + header_length
            payload_length = struct.unpack('>I', data[payload_offset:payload_offset+4])[0]
            
            if len(data) < payload_offset + 4 + payload_length:  # Not enough data for complete payload
                return None
            
            # Read payload
            payload = data[payload_offset+4:payload_offset+4+payload_length]
            
            return Packet(header, payload)
            
        except Exception as e:
            print(f"Error deserializing packet: {e}")
            return None
    
    @staticmethod
    def get_packet_size(data: bytes) -> Optional[int]:
        """
        Calculate total packet size from data buffer.
        Returns the number of bytes needed for a complete packet, or None if not enough data.
        """
        try:
            if len(data) < 8:
                return None
            
            header_length = struct.unpack('>I', data[0:4])[0]
            
            if len(data) < 4 + header_length + 4:
                return None
            
            payload_offset = 4 + header_length
            payload_length = struct.unpack('>I', data[payload_offset:payload_offset+4])[0]
            
            total_size = payload_offset + 4 + payload_length
            return total_size
            
        except Exception:
            return None
    
    def __repr__(self):
        return f"Packet({self.header}, payload_size={len(self.payload)})"


def generate_event_id(timestamp: float) -> str:
    """
    Generate event ID from timestamp.
    Format: "XXXXXXXX.XX" (8 digits before decimal, 2 after)
    Uses modulo to keep only last 8 digits for shorter IDs.
    
    Args:
        timestamp: Float from time.time()
    
    Returns:
        Event ID string
    """
    return f"{timestamp % 100000000:08.2f}"


def extract_timestamp_from_event_id(event_id: str) -> float:
    """
    Extract timestamp from event ID.
    
    Args:
        event_id: Event ID string in format "XXXXXX.XX"
    
    Returns:
        Float timestamp
    """
    return float(event_id)
