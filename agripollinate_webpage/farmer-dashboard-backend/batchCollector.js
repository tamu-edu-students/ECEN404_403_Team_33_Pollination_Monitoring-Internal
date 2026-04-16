const fs = require('fs');
const path = require('path');

class BatchCollector {
    constructor(baseDir) {
        this.baseDir = path.join(baseDir, '..', 'training_batches');
        if (!fs.existsSync(this.baseDir)) fs.mkdirSync(this.baseDir, { recursive: true });
        
        this.batchDir = null;
        this.count = 0;
        this.newBatch();
    }

    newBatch() {
        const id = Date.now();
        this.batchDir = path.join(this.baseDir, `batch_${id}`);
        fs.mkdirSync(path.join(this.batchDir, 'images'), { recursive: true });
        fs.mkdirSync(path.join(this.batchDir, 'labels'), { recursive: true });
        this.count = 0;
        console.log(`[BATCH] New batch: batch_${id}`);
    }

    add(imageBuffer, eventId, detections, confidenceThreshold = 0.5) {

        // Filter detections by confidence threshold 
        const filteredDetections = detections.filter(d => d.confidence >= confidenceThreshold);
        
        // Skip if no detections
        if (!filteredDetections || filteredDetections.length === 0) {
            console.log(`[BATCH] Skipping event ${eventId} - no detections above threshold`);
            return;
        }

        // Save image
        fs.writeFileSync(
            path.join(this.batchDir, 'images', `${eventId}.jpg`),
            imageBuffer
        );

        // Save YOLO labels
        const labels = filteredDetections.map(d => {
            const [x1, y1, x2, y2] = d.bbox;
            const cx = ((x1 + x2) / 2) / 640;
            const cy = ((y1 + y2) / 2) / 640;
            const w = (x2 - x1) / 640;
            const h = (y2 - y1) / 640;
            const classMap = {
                'bee': 0,
                'beetle': 1,
                'butterfly': 2,
                'grasshopper': 3,
                'ladybug': 4
            };
            const cls = classMap[d.class_name.toLowerCase()] ?? 0;
            return `${cls} ${cx.toFixed(6)} ${cy.toFixed(6)} ${w.toFixed(6)} ${h.toFixed(6)}`;
        }).join('\n');

        fs.writeFileSync(
            path.join(this.batchDir, 'labels', `${eventId}.txt`),
            labels
        );

        this.count++;
        
        // Rotate every 50 detections
        if (this.count >= 50) {
            this.newBatch();
        }
    }

    list() {
        return fs.readdirSync(this.baseDir).filter(f => f.startsWith('batch_'));
    }
}

module.exports = BatchCollector;