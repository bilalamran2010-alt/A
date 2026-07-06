import uuid
import sqlite3
import logging
import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

app = Flask(__name__, template_folder='templates')
app.secret_key = 'SUPER_SECURE_KEY_2026'

DB_NAME = "final_fix.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            max_devices INTEGER DEFAULT 1,
            devices_list TEXT DEFAULT '',
            expiry_date TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == "BILAL" and request.form.get("password") == "KING":
            session["logged_in"] = True
            return redirect(url_for("admin_page"))
    return render_template("login.html")

@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        action = request.form.get("action")
        key_name = request.form.get("key_name")

        if action == "generate":
            name = key_name or f"KEY-{uuid.uuid4().hex[:8].upper()}"
            days = int(request.form.get("days", 0))
            hours = int(request.form.get("hours", 0))
            minutes = int(request.form.get("minutes", 0))
            max_d = int(request.form.get("max_devices", 1))

            total_duration = timedelta(days=days, hours=hours, minutes=minutes)
            expiry_date = (datetime.now() + total_duration).strftime('%Y-%m-%d %H:%M:%S')

            try:
                conn.execute("INSERT INTO keys (key, max_devices, expiry_date, status) VALUES (?, ?, ?, 'active')",
                             (name, max_d, expiry_date))
                conn.commit()
            except Exception as e:
                app.logger.error(f"Error: {e}")

        elif action == "reset_hwid":
            conn.execute("UPDATE keys SET devices_list = '' WHERE key = ?", (key_name,))
            conn.commit()

        elif action == "delete_key":
            conn.execute("DELETE FROM keys WHERE key = ?", (key_name,))
            conn.commit()

        elif action == "clear_all":
            conn.execute("DELETE FROM keys")
            conn.commit()

        conn.close()
        return redirect(url_for("admin_page"))

    rows = conn.execute("SELECT key, max_devices, devices_list, expiry_date FROM keys").fetchall()
    conn.close()

    keys_list = []
    for r in rows:
        key_name, max_dev, devices_list, expiry_str = r
        used_dev = len([d for d in devices_list.split(',') if d])
        keys_list.append({
            "name": key_name,
            "devices": max_dev,
            "used": used_dev,
            "expiry": expiry_str
        })

    return render_template("admin.html", keys=keys_list)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

@app.route("/v", methods=["POST"])
def verify():
    data = request.get_json()
    user_key = data.get("key") if data else request.form.get("key")

    if not user_key:
        return jsonify({"status": False, "message": "Key required"})

    conn = get_db_connection()
    key_exists = conn.execute("SELECT 1 FROM keys WHERE key = ?", (user_key,)).fetchone()
    conn.close()

    if not key_exists:
        return jsonify({"status": False, "message": "INVALID KEY"})

    return jsonify({
        "status": True, 
        "data": {
            "real": "FreeFire-TMR-30DAY-77265e3273a43591-Vm8Lk7Uj2JmsjCPVPVjrLa7zgfx3uz9E",
            "token": "1177bde819e4cefe3a352b1dba108b45",
            "modname": "VIP MOD",
            "mod_status": "Safe",
            "credit": "MOD STATUS :- 100% SAFE",
            "ESP": "on",
            "Item": "on",
            "AIM": "on",
            "SilentAim": "on",
            "BulletTrack": "on",
            "Floating": "on",
            "Memory": "on",
            "Setting": "on",
            "expired_date": "2026-08-05 19:00:03",
            "EXP": "2026-08-05 19:00:03",
            "exdate": "2026-08-05 19:00:03",
            "device": "999999",
            "rng": 1783347116
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    