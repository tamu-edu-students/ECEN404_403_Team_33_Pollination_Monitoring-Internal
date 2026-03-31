## 🐍 ML Service Setup

### Prerequisites
- Python 3.8+
- pip

### Setup

1. **Navigate to the ml folder**
```bash
   cd ml
```

2. **Create a virtual environment**
```bash
   python3 -m venv venv
```

3. **Activate the virtual environment**
```bash
   # Mac/Linux
   source venv/bin/activate

   # Windows
   venv\Scripts\activate
```

4. **Install dependencies**
```bash
   pip install fastapi uvicorn ultralytics pillow torch torchvision python-multipart
```

5. **Run the ML server**
```bash
   python ml.py
```

   You should see:
```
   ✅ Model loaded successfully!
   🚀 Starting FastAPI ML Detection Service...
```

### Notes
- The server runs on `http://localhost:5000`
- To stop the environment when done: `deactivate`
- `venv/` is gitignored — each developer must set it up locally