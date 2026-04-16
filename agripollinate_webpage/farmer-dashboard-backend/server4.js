require('dotenv').config();
const { exec } = require('child_process');
const net = require('net');
const fs = require('fs');
const path = require('path');
const express = require('express');
const cors = require('cors');
const fetch = require('node-fetch');
const FormData = require('form-data'); 
const BatchCollector = require('./batchCollector');


const app = express();
app.use(cors());
app.use(express.json());

// --- CONFIGURATION ---
const raspberryPiHost = process.env.RASPBERRY_PI_HOST || '10.250.76.217';
const raspberryPiPort = process.env.RASPBERRY_PI_PORT || 12345;
const httpPort = process.env.PORT || 3000;
const ML_SERVICE_URL = process.env.ML_SERVICE_URL || 'http://localhost:5000';
const downloadDir = process.env.DOWNLOAD_DIR || path.join(__dirname, 'downloads');
const CONFIDENCE_THRESHOLD = 0.5;

if (!fs.existsSync(downloadDir)) fs.mkdirSync(downloadDir);

// Initialize batch collector
const batchCollector = new BatchCollector(downloadDir);

// Packet ID Constants
const PACKET_ID_IMAGE_OUTGOING = 1050;
const PACKET_ID_IMAGE_RESPONSE = 2050;
const PACKET_ID_LIDAR_RESPONSE = 2025;

// --- PACKET PROTOCOL CLASSES ---

class PacketHeader {
    constructor(event_id, packet_id) {
        this.event_id = event_id;
        this.packet_id = packet_id;
    }

    toJSON() {
        return JSON.stringify({
            event_id: this.event_id,
            packet_id: this.packet_id
        });
    }

    static fromJSON(json_str) {
        const data = JSON.parse(json_str);
        return new PacketHeader(data.event_id, data.packet_id);
    }
}

class Packet {
    constructor(header, payload = Buffer.alloc(0)) {
        this.header = header;
        this.payload = payload;
    }

    serialize() {
        const header_json = this.header.toJSON();
        const header_bytes = Buffer.from(header_json, 'utf-8');
        
        let serialized = Buffer.alloc(4);
        serialized.writeUInt32BE(header_bytes.length, 0);
        serialized = Buffer.concat([serialized, header_bytes]);
        
        let payload_length = Buffer.alloc(4);
        payload_length.writeUInt32BE(this.payload.length, 0);
        serialized = Buffer.concat([serialized, payload_length, this.payload]);
        
        return serialized;
    }

    static deserialize(data) {
        try {
            if (data.length < 8) return null;
            
            const header_length = data.readUInt32BE(0);
            if (data.length < 4 + header_length + 4) return null;
            
            const header_bytes = data.slice(4, 4 + header_length);
            const header_json = header_bytes.toString('utf-8');
            const header = PacketHeader.fromJSON(header_json);
            
            const payload_offset = 4 + header_length;
            const payload_length = data.readUInt32BE(payload_offset);
            
            if (data.length < payload_offset + 4 + payload_length) return null;
            
            const payload = data.slice(payload_offset + 4, payload_offset + 4 + payload_length);
            
            return new Packet(header, payload);
        } catch (e) {
            console.error(`[ERROR] Failed to deserialize packet: ${e}`);
            return null;
        }
    }

    static getPacketSize(data) {
        try {
            if (data.length < 8) return null;
            
            const header_length = data.readUInt32BE(0);
            if (data.length < 4 + header_length + 4) return null;
            
            const payload_offset = 4 + header_length;
            const payload_length = data.readUInt32BE(payload_offset);
            
            return payload_offset + 4 + payload_length;
        } catch (e) {
            return null;
        }
    }
}

function generateEventId(timestamp) {
    return (timestamp % 100000000).toFixed(2).padStart(10, '0');
}

// --- ML SERVICE INTEGRATION ---

async function checkMLService() {
    try {
        const response = await fetch(`${ML_SERVICE_URL}/health`);
        const data = await response.json();
        console.log('✅ ML Service connected:', data);
        return true;
    } catch (error) {
        console.warn('⚠️  ML Service not available:', error.message);
        return false;
    }
}

async function detectObjects(imageBuffer, filename, eventId) {
    try {
        const form = new FormData();
        form.append('file', imageBuffer, {
            filename: filename,
            contentType: 'image/jpeg'
        });

        const response = await fetch(`${ML_SERVICE_URL}/detect`, {
            method: 'POST',
            body: form,
            headers: form.getHeaders(),
        });

        if (!response.ok) {
            throw new Error(`ML detection failed: ${response.statusText}`);
        }

        const data = await response.json();
        
        // Save annotated image from base64
        if (data.annotated_image_base64) {
            const annotatedBuffer = Buffer.from(data.annotated_image_base64, 'base64');
            
            const annotatedFilename = `annotated_${filename}`;
            const annotatedPath = path.join(downloadDir, annotatedFilename);
            fs.writeFileSync(annotatedPath, annotatedBuffer);
            
            console.log(`[ML] Saved annotated image: ${annotatedFilename}`);
            data.annotated_filename = annotatedFilename;
        }

        return data;
    } catch (error) {
        console.error(`[ML] Detection error:`, error.message);
        return null;
    }
}

async function sendClassificationsToPi(eventId, detections) {
    try {
        const header = new PacketHeader(eventId, PACKET_ID_IMAGE_RESPONSE);
        
        // Filter detections by confidence threshold
        const validDetections = detections.filter(det => det.confidence >= CONFIDENCE_THRESHOLD);
        
        // Handle case when no insects detected or no detections meet threshold
        if (!validDetections || validDetections.length === 0) {
            const payload = JSON.stringify({
                detections: [],
                total_detections: 0,
                message: detections.length > 0 
                    ? `${detections.length} detection(s) below confidence threshold (${CONFIDENCE_THRESHOLD})`
                    : "No insects detected",
                timestamp: new Date().toISOString()
            });
            
            const jsonFilename = `classifications_${eventId}_${Date.now()}.json`;
            const jsonPath = path.join(downloadDir, jsonFilename);
            fs.writeFileSync(jsonPath, payload);

            const packet = new Packet(header, Buffer.from(payload, 'utf-8'));
            sendPacketToPi(packet);
            
            console.log(`[ML] Sent "no valid detections" message to Pi for event ${eventId}`);
            return;
        }
        
        // Send valid detections to Pi
        const payload = JSON.stringify({
            detections: validDetections.map(det => ({
                class_id: det.class_id,
                class_name: det.class_name,
                confidence: det.confidence,
                bbox: det.bbox
            })),
            total_detections: validDetections.length,
            timestamp: new Date().toISOString()
        });

        const jsonFilename = `classifications_${eventId}_${Date.now()}.json`;
        const jsonPath = path.join(downloadDir, jsonFilename);
        fs.writeFileSync(jsonPath, payload);

        const packet = new Packet(header, Buffer.from(payload, 'utf-8'));
        sendPacketToPi(packet);
        
        console.log(`[ML] Sent ${validDetections.length} classifications to Pi for event ${eventId}:`);
        validDetections.forEach((det, idx) => {
            console.log(`  ${idx + 1}. ${det.class_name} (ID: ${det.class_id}, Conf: ${(det.confidence * 100).toFixed(1)}%)`);
        });
    } catch (error) {
        console.error(`[ML] Error sending classifications to Pi:`, error);
    }
}

// --- TCP CLIENT TO CONNECT TO RASPBERRY PI ---

let piSocket = null;
let piBuffer = Buffer.alloc(0);

function connectToRaspberryPi() {
    piSocket = net.createConnection(raspberryPiPort, raspberryPiHost, () => {
        console.log(`Connected to server at ${raspberryPiHost}:${raspberryPiPort}`);
    });

    piSocket.on('data', (data) => {
        piBuffer = Buffer.concat([piBuffer, data]);

        while (piBuffer.length > 0) {
            const packet_size = Packet.getPacketSize(piBuffer);
            
            if (packet_size === null) {
                return;
            }

            if (piBuffer.length < packet_size) {
                return;
            }

            const packet_data = piBuffer.slice(0, packet_size);
            piBuffer = piBuffer.slice(packet_size);

            console.log(`[DEBUG] Deserializing complete packet of ${packet_size} bytes`);

            const packet = Packet.deserialize(packet_data);
            if (!packet) {
                console.error(`[ERROR] Failed to deserialize packet of size ${packet_size}`);
                console.error(`[ERROR] First 100 bytes (hex): ${packet_data.slice(0, 100).toString('hex')}`);
                console.error(`[ERROR] Discarding ${packet_data.length} bytes of corrupted data`);
                continue;
            }

            handlePacket(packet);
        }
    });

    piSocket.on('end', () => {
        console.log('Server closed connection, reconnecting in 5s...');
        piSocket = null;
        setTimeout(connectToRaspberryPi, 5000); // retry after 5 seconds
    });

    piSocket.on('error', (err) => {
        console.error(`Connection error: ${err.message}, reconnecting in 5s...`);
        piSocket = null;
        setTimeout(connectToRaspberryPi, 5000); // retry after 5 seconds
    });
}

function handlePacket(packet) {
    if (packet.header.packet_id === PACKET_ID_IMAGE_OUTGOING) {
        handleImagePacket(packet);
    } else if (packet.header.packet_id === PACKET_ID_IMAGE_RESPONSE) {
        handleImageResponse(packet);
    } else if (packet.header.packet_id === PACKET_ID_LIDAR_RESPONSE) {
        handleLidarResponse(packet);
    } else {
        console.log(`[BACKEND] Received unknown packet type: ${packet.header.packet_id}`);
    }
}

const detectionCache = new Map();

async function handleImagePacket(packet) {
    try {
        if (!fs.existsSync(downloadDir)) {
            fs.mkdirSync(downloadDir);
        }
        
        const now = new Date();
        const date = `${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}-${now.getFullYear()}`;
        const time = `${String(now.getHours()).padStart(2, '0')}.${String(now.getMinutes()).padStart(2, '0')}.${String(now.getSeconds()).padStart(2, '0')}.${String(now.getMilliseconds()).padStart(3, '0')}`;
        
        const filename = `received_${packet.header.event_id}_${date}_${time}.jpg`;
        const file_path = path.join(downloadDir, filename);
        
        // Save original image
        fs.writeFileSync(file_path, packet.payload);
        console.log(`[IMAGE] Received and saved: ${filename}, event_id: ${packet.header.event_id}`);
        
        // Automatically send to ML service for detection
        console.log(`[ML] Processing image ${filename}...`);
        const detectionResult = await detectObjects(packet.payload, filename, packet.header.event_id);
        
        if (detectionResult && detectionResult.success) {
            console.log(`[ML] ✅ Detected ${detectionResult.total_detections} objects`);
            detectionResult.detections.forEach((det, idx) => {
                console.log(`  ${idx + 1}. ${det.class_name} (${(det.confidence * 100).toFixed(1)}%)`);
            });

            // Store detection result in cache (in-memory)
            if (detectionResult.annotated_filename) {
                detectionCache.set(detectionResult.annotated_filename, detectionResult);
                console.log(`[CACHE] Saved detection result: ${detectionResult.annotated_filename}.json`);
            }

            try {
                batchCollector.add(packet.payload, packet.header.event_id, detectionResult.detections, CONFIDENCE_THRESHOLD);
            } catch (batchErr) {
                console.error('[BATCH] Error during batch collection:', batchErr);
            }
            
            // Send classifications back to Raspberry Pi
            await sendClassificationsToPi(packet.header.event_id, detectionResult.detections.filter(d => d.confidence >= CONFIDENCE_THRESHOLD));
        } else {
            console.log(`[ML] ❌ Detection failed for ${filename}`);
            // Still send empty detections
            await sendClassificationsToPi(packet.header.event_id, []);
        }
        
    } catch (e) {
        console.error(`Error handling image packet: ${e}`);
    }
}

function handleImageResponse(packet) {
    try {
        const payload_data = JSON.parse(packet.payload.toString('utf-8'));
        console.log(`[IMAGE RESPONSE] Event ${packet.header.event_id}: ${JSON.stringify(payload_data)}`);
    } catch (e) {
        console.error(`Error parsing image response: ${e}`);
    }
}

function handleLidarResponse(packet) {
    try {
        if (!fs.existsSync(downloadDir)) {
            fs.mkdirSync(downloadDir);
        }

        const payload = packet.payload;

        // Check if payload has the new structured format (PNG len prefix + JSON)
        // or is raw PNG (starts with PNG magic bytes 0x89504E47)
        const isRawPNG = payload[0] === 0x89 && payload[1] === 0x50 &&
                         payload[2] === 0x4E && payload[3] === 0x47;

        let pngBytes = payload;
        let pollinatorDetected = null;

        if (!isRawPNG) {
            // New structured format: [4-byte png_len][png_bytes][json_bytes]
            const pngLen = payload.readUInt32BE(0);
            pngBytes = payload.slice(4, 4 + pngLen);
            const jsonBytes = payload.slice(4 + pngLen);
            const detectionJson = JSON.parse(jsonBytes.toString('utf-8'));
            pollinatorDetected = detectionJson.pollinator_detected;
            console.log(`[IMAGE CLIENT] Pollinator Detected: ${pollinatorDetected}`);
        }

        const filename = `pollinator_activity_map_${packet.header.event_id}.png`;
        const file_path = path.join(downloadDir, filename);
        fs.writeFileSync(file_path, pngBytes);
        console.log(`[LIDAR] Saved: ${filename} (${pngBytes.length} bytes)`);

        const isPNG = pngBytes[0] === 0x89 && pngBytes[1] === 0x50 &&
                      pngBytes[2] === 0x4E && pngBytes[3] === 0x47;
        console.log(`[LIDAR] Is valid PNG: ${isPNG}`);

    } catch (e) {
        console.error(`Error handling lidar response: ${e}`);
    }
}

function sendPacketToPi(packet) {
    if (!piSocket || piSocket.destroyed) {
        console.error(`Could not send packet - not connected to server`);
        return false;
    }
    piSocket.write(packet.serialize());
    console.log(`[BACKEND] Sent packet (${packet.header.packet_id}), event_id: ${packet.header.event_id}`);
    return true;
}

// --- HELPER FUNCTIONS ---

function getLatestImages(n = 5) {
    try {
        const files = fs.readdirSync(downloadDir);
        const images = files.filter(f => /\.(jpe?g|png)$/i.test(f));
        const withTime = images.map(f => ({
            file: f,
            mtime: fs.statSync(path.join(downloadDir, f)).mtime.getTime()
        }));
        withTime.sort((a, b) => b.mtime - a.mtime);
        return withTime.slice(0, n).map(obj => obj.file);
    } catch (err) {
        console.error("Error reading images:", err);
        return [];
    }
}

function getImagePairs(n = 10) {
    try {
        const files = fs.readdirSync(downloadDir);
        const receivedImages = files.filter(f => f.startsWith('received_') && /\.jpe?g$/i.test(f));
        
        const pairs = receivedImages.map(original => {
            const annotated = `annotated_${original}`;
            const hasAnnotated = files.includes(annotated);
            
            return {
                original,
                annotated: hasAnnotated ? annotated : null,
                eventId: original.match(/received_(\d+)_/)?.[1] || 'unknown',
                mtime: fs.statSync(path.join(downloadDir, original)).mtime.getTime()
            };
        });
        
        pairs.sort((a, b) => b.mtime - a.mtime);
        return pairs.slice(0, n);
    } catch (err) {
        console.error("Error reading image pairs:", err);
        return [];
    }
}

// --- EXPRESS HTTP API ---
app.use('/images', (req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    next();
});
app.use('/images', express.static(downloadDir));

// Get list of latest images (both original and annotated)
app.get('/images/list', (req, res) => {
    const pairs = getImagePairs(1);
    res.json(pairs);
});

// Get latest annotated images only
app.get('/images/annotated', (req, res) => {
    const pairs = getImagePairs(1);
    const annotated = pairs
        .filter(p => p.annotated)
        .map(p => p.annotated);
    res.json(annotated);
});

// Get LIDAR heatmaps
app.get('/images/lidar', (req, res) => {
    try {
        const files = fs.readdirSync(downloadDir);
        const lidarMaps = files.filter(f => f.startsWith('pollinator_activity_map_') && f.endsWith('.png'));
        const withTime = lidarMaps.map(f => ({
            filename: f,
            eventId: f.match(/pollinator_activity_map_(\d+)\.png/)?.[1] || 'unknown',
            mtime: fs.statSync(path.join(downloadDir, f)).mtime.getTime()
        }));
        withTime.sort((a, b) => b.mtime - a.mtime);
        res.json(withTime.slice(0, 10));
    } catch (err) {
        console.error("Error reading LIDAR maps:", err);
        res.json([]);
    }
});

// Endpoint to trigger detection on a specific image (if not already cached)
app.post('/detect-image', async (req, res) => {
    const { filename } = req.body;
    
    if (!filename) {
        return res.status(400).json({ error: 'Filename required' });
    }
    
    const imagePath = path.join(downloadDir, filename);
    
    if (!fs.existsSync(imagePath)) {
        return res.status(404).json({ error: 'Image not found' });
    }
    
    if (detectionCache.has(filename)) {
        console.log(`[CACHE HIT] ${filename}`);
        return res.json(detectionCache.get(filename));
    }
    
    console.log(`[CACHE MISS] Running detection for ${filename}...`);
    try {
        const imageBuffer = fs.readFileSync(imagePath);
        const eventId = filename.match(/received_(\d+)_/)?.[1] || generateEventId(Date.now() / 1000);
        const result = await detectObjects(imageBuffer, filename, eventId);
        
        if (result && result.detections) {
            result.detections = result.detections.filter(det => det.confidence >= CONFIDENCE_THRESHOLD);
            result.total_detections = result.detections.length;
            
            const cacheFilePath = `${imagePath}.json`;
            fs.writeFileSync(cacheFilePath, JSON.stringify(result, null, 2));
            console.log(`[CACHE] Saved filtered detection result: ${filename}.json`);
        }
        
        res.json(result || { error: 'Detection failed' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// List all batches
app.get('/api/batches', (req, res) => {
    try {
        const batches = batchCollector.list();
        res.json({ success: true, batches });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// --- START SERVERS ---

// Check ML service availability after delay
setTimeout(() => {
    checkMLService();
}, 3000);

// Connect to Raspberry Pi on startup
connectToRaspberryPi();
console.log("Waiting for packets from Raspberry Pi... (Ctrl+C to quit)\n");

app.listen(httpPort, () => {
    console.log(`\n🚀 Express server running at http://localhost:${httpPort}`);
    console.log(`📁 Image files served from: ${downloadDir}`);
    console.log(`🤖 ML service expected at: ${ML_SERVICE_URL}\n`);
});