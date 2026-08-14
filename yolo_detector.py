import cv2
import numpy as np
import os
import time
from datetime import datetime
from ultralytics import YOLO
from database import log_breach, get_settings

CLASS_WIDTHS = {'person': 0.55, 'car': 1.80, 'bicycle': 0.60, 'motorcycle': 0.75, 'bus': 2.50, 'truck': 2.60, 'dog': 0.40}
DEFAULT_WIDTH = 0.50

class DistanceDetector:
    def __init__(self, model_name="yolov8n.pt"):
        self.model = YOLO(model_name)
        self.snapshots_dir = os.path.join("static", "uploads", "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)
        self.settings = get_settings()
        self.last_settings_update = 0

    def refresh_settings(self):
        if time.time() - self.last_settings_update > 5:
            self.settings = get_settings()
            self.last_settings_update = time.time()

    def get_corridor_points(self, w, h):
        # Safety lane trapezoid boundaries
        return np.array([[int(w * 0.18), int(h * 0.95)], [int(w * 0.82), int(h * 0.95)], 
                         [int(w * 0.58), int(h * 0.55)], [int(w * 0.42), int(h * 0.55)]], dtype=np.int32)

    def process_frame(self, frame):
        self.refresh_settings()
        safety_thr = float(self.settings.get("safety_threshold", 5.0))
        warning_thr = float(self.settings.get("warning_threshold", 10.0))
        min_conf = float(self.settings.get("min_confidence", 0.4))
        active_cls = [c.strip() for c in self.settings.get("active_classes", "").split(",") if c.strip()]

        h, w = frame.shape[:2]
        corridor = self.get_corridor_points(w, h)
        overlay = frame.copy()
        
        results = self.model(frame, conf=min_conf, verbose=False)[0]
        alert_triggered, alert_msg, highest_sev = False, "", ""
        detected_objs, lane_breached = [], False

        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            class_name = self.model.names[int(box.cls[0].cpu().item())]
            
            if class_name not in active_cls:
                continue

            bbox_w, bbox_h = x2 - x1, y2 - y1
            bottom_center = (int(x1 + bbox_w / 2), y2)
            
            # Distance estimation: D = (W_real * Focal) / W_pixel
            focal = w * float(self.settings.get("focal_length_factor", 1.2))
            dist = (CLASS_WIDTHS.get(class_name, DEFAULT_WIDTH) * focal) / max(bbox_w, 1)
            
            inside_lane = cv2.pointPolygonTest(corridor, (float(bottom_center[0]), float(bottom_center[1])), False) >= 0
            status, box_color = "SAFE", (0, 255, 0)

            if dist <= safety_thr:
                status, box_color, lane_breached = "CRITICAL", (0, 0, 255), True
                alert_triggered = True
                highest_sev = "CRITICAL"
                alert_msg = f"CRITICAL: Close {class_name} at {dist:.1f}m!"
            elif dist <= warning_thr:
                status, box_color = "WARNING", (0, 165, 255)
                if highest_sev != "CRITICAL":
                    highest_sev, alert_msg = "WARNING", f"WARNING: Close {class_name} at {dist:.1f}m!"
                alert_triggered = True

            if status in ["CRITICAL", "WARNING"]:
                snap_name = f"breach_{class_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                snap_path = os.path.join(self.snapshots_dir, snap_name)
                
                # Crop event thumbnail
                margin_h, margin_w = int(bbox_h * 0.15), int(bbox_w * 0.15)
                crop = frame[max(0, y1-margin_h):min(h, y2+margin_h), max(0, x1-margin_w):min(w, x2+margin_w)]
                if crop.size > 0:
                    cv2.imwrite(snap_path, crop)
                    db_snap_path = f"uploads/snapshots/{snap_name}"
                else:
                    db_snap_path = None
                    
                log_breach(class_name, dist, status, db_snap_path)

            # Draw boxes
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.circle(frame, bottom_center, 4, box_color, -1)
            
            label = f"{class_name.upper()} {dist:.1f}m"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.rectangle(frame, (x1, y1 - lh - 6), (x1 + lw + 6, y1), box_color, -1)
            cv2.putText(frame, label, (x1 + 3, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            
            detected_objs.append({"class": class_name, "distance": dist, "status": status, "in_lane": inside_lane})

        # Draw transparent lane corridor overlay
        cor_color = (0, 0, 255) if lane_breached else ((0, 165, 255) if highest_sev == "WARNING" else (0, 255, 0))
        cv2.fillPoly(overlay, [corridor], cor_color)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        cv2.polylines(frame, [corridor], True, cor_color, 2, cv2.LINE_AA)
        cv2.putText(frame, "SAFETY ZONE", (corridor[3][0] - 40, corridor[3][1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, cor_color, 1, cv2.LINE_AA)

        if alert_triggered:
            cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 255) if highest_sev == "CRITICAL" else (0, 165, 255), -1)
            alert_txt = f"!!! HAZARD DETECTED !!! {alert_msg.upper()}"
            tw = cv2.getTextSize(alert_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0][0]
            cv2.putText(frame, alert_txt, (int((w - tw) / 2), 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

        return frame, {"alert": alert_triggered, "message": alert_msg, "severity": highest_sev, "objects": detected_objs}
