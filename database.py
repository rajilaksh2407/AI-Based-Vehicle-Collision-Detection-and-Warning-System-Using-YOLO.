import sqlite3, os
from datetime import datetime

DB_NAME = "safety_tracker.db"

def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS safety_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            object_type TEXT NOT NULL, distance REAL NOT NULL, severity TEXT NOT NULL, snapshot_path TEXT)""")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)")
        if conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            defaults = [("safety_threshold", "5.0"), ("warning_threshold", "10.0"), ("focal_length_factor", "1.2"),
                        ("min_confidence", "0.4"), ("active_classes", "person,car,truck,bus,motorcycle,bicycle"), ("selected_video_source", "webcam")]
            conn.executemany("INSERT INTO settings VALUES (?, ?)", defaults)
        conn.commit()

def get_settings():
    with get_conn() as conn:
        return {r["setting_key"]: r["setting_value"] for r in conn.execute("SELECT * FROM settings").fetchall()}

def update_settings(settings_dict):
    with get_conn() as conn:
        for k, v in settings_dict.items():
            conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (k, str(v)))
        conn.commit()

def log_breach(obj, dist, sev, snap=None):
    with get_conn() as conn:
        recent = conn.execute("SELECT timestamp FROM safety_logs WHERE object_type=? AND severity=? AND distance BETWEEN ? AND ? ORDER BY timestamp DESC LIMIT 1",
                              (obj, sev, dist-0.5, dist+0.5)).fetchone()
        if recent and (datetime.now() - datetime.strptime(recent["timestamp"], "%Y-%m-%d %H:%M:%S")).total_seconds() < 2.0:
            return
        conn.execute("INSERT INTO safety_logs (timestamp, object_type, distance, severity, snapshot_path) VALUES (?, ?, ?, ?, ?)",
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), obj, round(dist, 2), sev, snap))
        conn.commit()

def get_logs(limit=100, offset=0, sev=None, cls=None):
    query, params = "SELECT * FROM safety_logs", []
    conds = []
    if sev: conds.append("severity=?"); params.append(sev)
    if cls: conds.append("object_type=?"); params.append(cls)
    if conds: query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]

def get_log_stats():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM safety_logs").fetchone()[0]
        sevs = {r["severity"]: r["count"] for r in conn.execute("SELECT severity, COUNT(*) as count FROM safety_logs GROUP BY severity").fetchall()}
        objs = {r["object_type"]: r["count"] for r in conn.execute("SELECT object_type, COUNT(*) as count FROM safety_logs GROUP BY object_type").fetchall()}
        avg_d, min_d = conn.execute("SELECT AVG(distance), MIN(distance) FROM safety_logs").fetchone()
        return {
            "total_logs": total, "severities": sevs, "objects": objs,
            "avg_distance": round(avg_d, 2) if avg_d else 0.0, "min_distance": round(min_d, 2) if min_d else 0.0
        }

def clear_logs():
    with get_conn() as conn:
        conn.execute("DELETE FROM safety_logs")
        conn.commit()
