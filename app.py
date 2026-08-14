import os, time, urllib.request, threading, json, cv2, database
from flask import Flask, render_template, Response, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from yolo_detector import DistanceDetector

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads", "videos")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join("static", "videos"), exist_ok=True)

class VideoStreamManager:
    def __init__(self):
        self.cap, self.detector, self.running = None, DistanceDetector(), False
        self.thread, self.lock = None, threading.Lock()
        self.current_source = "webcam"
        self.latest_frame = None
        self.latest_alert = {"alert": False, "message": "", "severity": "", "objects": []}
        
    def start(self, source="webcam"):
        with self.lock:
            if self.running: self.stop_current()
            self.current_source, self.running = source, True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop_current(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.5); self.thread = None
        if self.cap: self.cap.release(); self.cap = None
        self.latest_frame = None
        self.latest_alert = {"alert": False, "message": "", "severity": "", "objects": []}

    def _run(self):
        self.cap = cv2.VideoCapture(0) if self.current_source == "webcam" else cv2.VideoCapture(self.current_source)
        if not self.cap or not self.cap.isOpened(): self.running = False; return
        
        is_file = (self.current_source != "webcam")
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        frame_delay = 1.0 / fps

        while self.running:
            t0 = time.time()
            ret, frame = self.cap.read()
            if not ret:
                if is_file: self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0); continue
                time.sleep(1); continue
            
            # Downsize for performance
            h, w = frame.shape[:2]
            frame = cv2.resize(frame, (854, int((854 / w) * h)))
            annotated, alert_data = self.detector.process_frame(frame)
            ret, jpeg = cv2.imencode('.jpg', annotated)
            
            if ret:
                with self.lock:
                    self.latest_frame = jpeg.tobytes()
                    self.latest_alert = alert_data
            
            elapsed = time.time() - t0
            if is_file and frame_delay > elapsed:
                time.sleep(frame_delay - elapsed)
            else:
                time.sleep(0.01)

stream_manager = VideoStreamManager()

def download_sample_video():
    video_path = os.path.join("static", "videos", "car-detection.mp4")
    if not os.path.exists(video_path):
        url = "https://github.com/intel-iot-devkit/sample-videos/raw/master/car-detection.mp4"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as res, open(video_path, 'wb') as f:
                f.write(res.read())
        except Exception as e: print("Fail download video sample:", e)

@app.route("/")
def index(): return render_template("index.html")

def generate_video_feed():
    while True:
        frame = None
        with stream_manager.lock:
            if stream_manager.latest_frame: frame = stream_manager.latest_frame
        if frame:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            blank = np.zeros((480, 854, 3), dtype=np.uint8)
            cv2.putText(blank, "Initializing Stream...", (250, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            ret, jpeg = cv2.imencode('.jpg', blank)
            if ret: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(0.04)

@app.route("/video_feed")
def video_feed(): return Response(generate_video_feed(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/api/active_alert")
def active_alert():
    with stream_manager.lock: return jsonify(stream_manager.latest_alert)

@app.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    if request.method == "POST":
        database.update_settings(request.json)
        stream_manager.detector.refresh_settings()
        return jsonify({"status": "success"})
    return jsonify(database.get_settings())

@app.route("/api/logs")
def get_logs():
    logs = database.get_logs(request.args.get("limit", 50, type=int), request.args.get("offset", 0, type=int), 
                             request.args.get("severity"), request.args.get("class"))
    return jsonify(logs)

@app.route("/api/logs/clear", methods=["POST"])
def clear_all_logs():
    database.clear_logs()
    snapshots_dir = os.path.join("static", "uploads", "snapshots")
    if os.path.exists(snapshots_dir):
        for f in os.listdir(snapshots_dir):
            try: os.unlink(os.path.join(snapshots_dir, f))
            except: pass
    return jsonify({"status": "success"})

@app.route("/api/stats")
def get_stats(): return jsonify(database.get_log_stats())

@app.route("/api/video_sources")
def get_video_sources():
    sources = [{"id": "webcam", "name": "USB Webcam (Live)", "path": "webcam"}]
    sample_path = os.path.join("static", "videos", "car-detection.mp4")
    if os.path.exists(sample_path):
        sources.append({"id": "sample_video", "name": "Sample Dashcam (Highway)", "path": sample_path})
    for f in os.listdir(app.config["UPLOAD_FOLDER"]):
        if f.endswith(('.mp4', '.avi', '.mov', '.mkv')):
            sources.append({"id": f"upload_{f}", "name": f"Uploaded: {f}", "path": os.path.join(app.config["UPLOAD_FOLDER"], f)})
    return jsonify({"current": stream_manager.current_source, "sources": sources})

@app.route("/api/change_source", methods=["POST"])
def change_source():
    data = request.json
    source_id = data.get("source_id")
    if source_id == "webcam":
        stream_manager.start("webcam")
        database.update_settings({"selected_video_source": "webcam"})
    elif source_id == "sample_video":
        p = os.path.join("static", "videos", "car-detection.mp4")
        stream_manager.start(p)
        database.update_settings({"selected_video_source": p})
    else:
        path = data.get("path")
        if path and os.path.exists(path):
            stream_manager.start(path)
            database.update_settings({"selected_video_source": path})
    return jsonify({"status": "success"})

@app.route("/api/upload_video", methods=["POST"])
def upload_video():
    file = request.files.get("file")
    if file and file.filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
        fname = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
        file.save(path)
        stream_manager.start(path)
        database.update_settings({"selected_video_source": path})
        return jsonify({"status": "success", "path": path})
    return jsonify({"status": "error", "message": "Invalid file"}), 400

@app.route("/static/uploads/snapshots/<filename>")
def serve_snapshot(filename):
    return send_from_directory(os.path.join("static", "uploads", "snapshots"), filename)

if __name__ == "__main__":
    database.init_db()
    download_sample_video()
    s = database.get_settings()
    src = s.get("selected_video_source", "webcam")
    if src != "webcam" and not os.path.exists(src):
        sample = os.path.join("static", "videos", "car-detection.mp4")
        src = sample if os.path.exists(sample) else "webcam"
    stream_manager.start(src)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
