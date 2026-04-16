from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import threading
import queue
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
process = None
output_lines = []
flower_response_queue = queue.Queue()
pending_flower = None
current_testing_mode = False

def run_main(testing: bool, auto_config: bool, skip_lidar_client: bool):
    global process, output_lines, pending_flower, current_testing_mode
    output_lines = []
    pending_flower = None
    current_testing_mode = testing

    process = subprocess.Popen(
        ["python", "master_main.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    def answer_prompts():
        global pending_flower

        for line in process.stdout:
            stripped = line.strip()
            output_lines.append(stripped)
            print(f"[PI] {stripped}")

            if "testing mode" in stripped.lower():
                response = 'y\n' if testing else 'n\n'
                try:
                    process.stdin.write(response)
                    process.stdin.flush()
                except BrokenPipeError:
                    print("[PI_SERVER] Process already exited")

            elif "auto-configure flower" in stripped.lower():
                response = 'y\n' if auto_config else 'n\n'
                try:
                    process.stdin.write(response)
                    process.stdin.flush()
                except BrokenPipeError:
                    print("[PI_SERVER] Process already exited")

            elif "without a lidar data client" in stripped.lower():
                if process and process.poll() is None:
                    response = 'y\n' if skip_lidar_client else 'n\n'
                    try:
                        process.stdin.write(response)
                        process.stdin.flush()
                    except BrokenPipeError:
                        print("[PI_SERVER] Process already exited, can't send lidar client response")

            elif "would you like to include this flower" in stripped.lower():
                pending_flower = stripped
                try:
                    response = flower_response_queue.get(timeout=60)
                    process.stdin.write(response + '\n')
                    process.stdin.flush()
                except queue.Empty:
                    print("[PI_SERVER] Flower response timed out, skipping")
                    process.stdin.write('n\n')
                    process.stdin.flush()
                finally:
                    pending_flower = None

    prompt_thread = threading.Thread(target=answer_prompts, daemon=True)
    prompt_thread.start()

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {"status": "healthy", "program_running": process is not None and process.poll() is None}

@app.post("/start")
def start_program(testing: bool = False, auto_config: bool = False, skip_lidar_client: bool = True):
    global process
    if process and process.poll() is None:
        return {"status": "already_running"}
   
    thread = threading.Thread(
        target=run_main,
        args=(testing, auto_config, skip_lidar_client),
        daemon=True
    )
    thread.start()
    return {"status": "started"}

@app.post("/stop")
def stop_program():
    global process
    if process and process.poll() is None:
        process.terminate()
        return {"status": "stopped"}
    return {"status": "not_running"}

@app.post("/trigger-event")
def trigger_event():
    global process
    if process and process.poll() is None:
        try:
            process.stdin.write('\n')
            process.stdin.flush()
            return {"status": "triggered"}
        except BrokenPipeError:
            return {"status": "error", "message": "Process pipe broken"}
    return {"status": "not_running"}

@app.get("/status")
def get_status():
    global process, output_lines, current_testing_mode
    return {
        "running": process is not None and process.poll() is None,
        "recent_logs": output_lines[-20:] if output_lines else [],
        "testing": current_testing_mode
    }

@app.get("/flower-pending")
def get_pending_flower():
    return {
        "pending": pending_flower is not None,
        "prompt": pending_flower
    }

@app.post("/flower-response")
def flower_response(include: bool = True):
    flower_response_queue.put('y' if include else 'n')
    return {"status": "ok"}