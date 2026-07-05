import uuid
import sqlite3
import logging
import os
from flask import Flask, request, render_template, session, redirect, url_for, make_response

logging.basicConfig(level=logging.INFO)

app = Flask(__name__, template_folder='templates')
app.secret_key = 'SUPER_SECURE_KEY_2026'
DB_NAME = "/home/bilal828/final_fix.db"

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
                app.logger.error(f"Error generating key: {e}")

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

        try:
            expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
            time_left = expiry_dt - datetime.now()
            if time_left.total_seconds() > 0:
                duration_string = f"{time_left.days}d {time_left.seconds // 3600}h {(time_left.seconds % 3600) // 60}m"
            else:
                duration_string = "Expired"
        except:
            duration_string = "Error"

        keys_list.append({
            "name": key_name,
            "devices": max_dev,
            "used": used_dev,
            "duration_string": duration_string
        })

    return render_template("admin.html", keys=keys_list)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

@app.route("/najmul", methods=["POST"])
def verify():
    key = request.form.get("user_key")
    device_id = request.form.get("serial")
    
    conn = get_db_connection()
    row = conn.execute("SELECT status FROM keys WHERE key = ?", (key,)).fetchone()
    conn.close()

    if not row:
        return "Error: Invalid"

    ENCRYPTED_RESPONSE = "MBLuvMSQJ2y3RvmpOU+JwU6XWtLjMXc6JGJc00Bc7M22ICkME2TdoFgQz2ucgbFopccHlGECqTrBKN4xZ687C7hfSjmPS64xWC6mFwcwUL4gMB6xjx4syTTTrUFlcxpMmSBgxhZS2JfUv4RqEIH7V10chZf0F8j7o436QUET6f8LDs1fvbJgBJ8tZAcjlCS5UE14/am3acoeW0lTkkvRqIRRykCmBV2Ps/gmaDP7Foax51IVAfG9A1Yt5X6sKMhSaQLDg=="
    
    response = make_response(ENCRYPTED_RESPONSE)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return response

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, threaded=True)
    