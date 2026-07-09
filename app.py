import os
import uuid
import sqlite3
import logging
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

app = Flask(__name__, template_folder='templates')
app.secret_key = 'SUPER_SECURE_KEY_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# تغيير اسم قاعدة البيانات لإنشاء نسخة نظيفة تماماً متوافقة مع الكود الجديد
DB_NAME = os.path.join(BASE_DIR, "core_production_v2.db")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # إنشاء جدول المفاتيح بالهيكلية الكاملة مباشرة
    conn.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            [key] TEXT UNIQUE NOT NULL,
            max_devices INTEGER DEFAULT 1,
            devices_list TEXT DEFAULT '',
            expiry_date TEXT,
            status TEXT DEFAULT 'active',
            panel_name TEXT DEFAULT 'Panel 07',
            owner TEXT DEFAULT 'BILAL'
        )''')
    
    # إنشاء جدول الإدارة
    conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'reseller',
            bound_hwid TEXT DEFAULT NULL
        )''')
    
    # الحسابات الافتراضية الثابتة
    default_users = [
        ("BILAL", "KING@", "master"),
        ("NOVA", "MBAZAL", "reseller"),
        ("UNIX", "L7AS", "reseller")
    ]

    for username, password, role in default_users:
        user_exists = conn.execute("SELECT 1 FROM admins WHERE username = ?", (username,)).fetchone()
        if not user_exists:
            conn.execute("INSERT INTO admins (username, password, role) VALUES (?, ?, ?)", (username, password, role))
        else:
            conn.execute("UPDATE admins SET password = ?, role = ? WHERE username = ?", (password, role, username))

    conn.commit()
    conn.close()

init_db()

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        browser_fingerprint = request.form.get("browser_fingerprint", "").strip()
        
        if not browser_fingerprint:
            browser_fingerprint = "UNKNOWN-HWID"

        conn = get_db_connection()
        user = conn.execute("SELECT role, bound_hwid FROM admins WHERE username = ? AND password = ?", (username, password)).fetchone()
        
        if user:
            role, bound_hwid = user['role'], user['bound_hwid']
            
            if bound_hwid is None or bound_hwid == "" or bound_hwid == "NULL":
                conn.execute("UPDATE admins SET bound_hwid = ? WHERE username = ?", (browser_fingerprint, username))
                conn.commit()
                bound_hwid = browser_fingerprint
            
            if role != "master" and bound_hwid != browser_fingerprint:
                conn.close()
                flash("Device Verification Failed! Locked to another hardware node.")
                return render_template("login.html")
            
            conn.close()
            session["logged_in"] = True
            session["username"] = username
            session["role"] = role
            return redirect(url_for("admin_page"))
            
        conn.close()
        flash("Invalid credentials! Please check your username and password.")
        return render_template("login.html")
        
    return render_template("login.html")

@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    current_user = session.get("username")
    current_role = session.get("role")

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        key_name = request.form.get("key_name", "").strip()

        if "max_devices" in request.form and ("days" in request.form or "hours" in request.form):
            action = "generate"
        elif "reseller_username" in request.form and "reseller_password" in request.form:
            if action not in ["delete_reseller", "reset_reseller_ip"]:
                action = "add_reseller"

        if key_name and action in ["edit_key", "reset_device", "delete_key"] and current_role != "master":
            key_owner = conn.execute("SELECT owner FROM keys WHERE [key] = ?", (key_name,)).fetchone()
            if key_owner and key_owner['owner'] != current_user:
                conn.close()
                return "<h1>Unauthorized Action</h1>", 403

        # 1. Generate Token
        if action == "generate":
            name = key_name if key_name != "" else f"KEY-{uuid.uuid4().hex[:8].upper()}"
            
            days = int(request.form.get("days") or 0)
            hours = int(request.form.get("hours") or 0)
            minutes = int(request.form.get("minutes") or 0)
            max_d = int(request.form.get("max_devices") or 1)
            
            raw_panel = request.form.get("panel_name", "Panel 07").strip()
            panel = "Panel 07" if "Panel 07" in raw_panel else raw_panel

            total_duration = timedelta(days=days, hours=hours, minutes=minutes)
            if total_duration.total_seconds() == 0:
                total_duration = timedelta(days=30)
                
            expiry_date = (datetime.now() + total_duration).strftime('%Y-%m-%d %H:%M:%S')

            try:
                conn.execute("INSERT INTO keys ([key], max_devices, expiry_date, status, panel_name, owner) VALUES (?, ?, ?, 'active', ?, ?)",
                             (name, max_d, expiry_date, panel, current_user))
                conn.commit()
            except Exception as e:
                app.logger.error(f"Error generating key: {e}")

        # 2. Edit Existing Token Config
        elif action == "edit_key":
            new_max = int(request.form.get("new_max_devices") or 1)
            raw_new_panel = request.form.get("new_panel", "Panel 07").strip()
            new_panel = "Panel 07" if "Panel 07" in raw_new_panel else raw_new_panel
            add_days = int(request.form.get("add_days") or 0)
            
            if add_days > 0:
                row = conn.execute("SELECT expiry_date FROM keys WHERE [key] = ?", (key_name,)).fetchone()
                if row:
                    try:
                        current_expiry = datetime.strptime(row['expiry_date'], '%Y-%m-%d %H:%M:%S')
                        base_time = current_expiry if current_expiry > datetime.now() else datetime.now()
                        new_expiry = (base_time + timedelta(days=add_days)).strftime('%Y-%m-%d %H:%M:%S')
                        conn.execute("UPDATE keys SET max_devices = ?, panel_name = ?, expiry_date = ? WHERE [key] = ?", 
                                     (new_max, new_panel, new_expiry, key_name))
                    except: pass
            else:
                conn.execute("UPDATE keys SET max_devices = ?, panel_name = ? WHERE [key] = ?", 
                             (new_max, new_panel, key_name))
            conn.commit()

        # 3. Reset Hardware Signature 
        elif action == "reset_device":
            conn.execute("UPDATE keys SET devices_list = '' WHERE [key] = ?", (key_name,))
            conn.commit()

        # 4. Revoke Key Entry
        elif action == "delete_key":
            conn.execute("DELETE FROM keys WHERE [key] = ?", (key_name,))
            conn.commit()

        # 5. Global Table Wipe Options
        elif action == "clear_all":
            if current_role == "master":
                conn.execute("DELETE FROM keys")
            else:
                conn.execute("DELETE FROM keys WHERE owner = ?", (current_user,))
            conn.commit()

        # 6. Instantiate Sub-Reseller Structures
        elif action == "add_reseller" and current_role == "master":
            r_user = request.form.get("reseller_username", "").strip()
            r_pass = request.form.get("reseller_password", "").strip()
            if r_user and r_pass:
                try:
                    conn.execute("INSERT INTO admins (username, password, role, bound_hwid) VALUES (?, ?, 'reseller', NULL)", (r_user, r_pass))
                    conn.commit()
                except Exception as e: 
                    app.logger.error(f"Error adding reseller: {e}")

        # 7. Unregister Sub-Resellers Completely
        elif action == "delete_reseller" and current_role == "master":
            target_reseller = request.form.get("reseller_username")
            if target_reseller and target_reseller != current_user:
                conn.execute("DELETE FROM admins WHERE username = ? AND role = 'reseller'", (target_reseller,))
                conn.execute("DELETE FROM keys WHERE owner = ?", (target_reseller,))
                conn.commit()

        # 8. Reset Bound IP Lock Fingerprints
        elif action == "reset_reseller_ip" and current_role == "master":
            target_reseller = request.form.get("reseller_username")
            if target_reseller:
                conn.execute("UPDATE admins SET bound_hwid = NULL WHERE username = ?", (target_reseller,))
                conn.commit()

        conn.close()
        return redirect(url_for("admin_page"))

    # جلب البيانات بشكل آمن لـ GET
    try:
        if current_role == "master":
            rows = conn.execute("SELECT [key], max_devices, devices_list, expiry_date, panel_name, owner FROM keys").fetchall()
        else:
            rows = conn.execute("SELECT [key], max_devices, devices_list, expiry_date, panel_name, owner FROM keys WHERE owner = ?", (current_user,)).fetchall()
    except Exception as e:
        app.logger.error(f"Database fetch error: {e}")
        rows = []
        
    keys_list = []
    for r in rows:
        used_dev = len([d for d in (r['devices_list'] or "").split(',') if d])
        try:
            expiry_dt = datetime.strptime(r['expiry_date'], '%Y-%m-%d %H:%M:%S')
            time_left = expiry_dt - datetime.now()
            if time_left.total_seconds() > 0:
                duration_string = f"{time_left.days}d {time_left.seconds // 3600}h {(time_left.seconds % 3600) // 60}m"
            else:
                duration_string = "Expired"
        except:
            duration_string = "Error"

        keys_list.append({
            "name": r['key'],
            "devices": r['max_devices'],
            "used": used_dev,
            "duration_string": duration_string,
            "panel_name": r['panel_name'],
            "owner": r['owner']
        })

    resellers_list = []
    if current_role == "master":
        try:
            reseller_rows = conn.execute("SELECT username, password, bound_hwid FROM admins WHERE role = 'reseller'").fetchall()
            for r_row in reseller_rows:
                key_count = conn.execute("SELECT COUNT(*) FROM keys WHERE owner = ?", (r_row['username'],)).fetchone()[0]
                resellers_list.append({
                    "username": r_row['username'],
                    "password": r_row['password'],
                    "bound_ip": r_row['bound_hwid'] or "Not Logged In Yet",
                    "key_count": key_count
                })
        except Exception as e:
            app.logger.error(f"Reseller fetch error: {e}")

    conn.close()
    return render_template("admin.html", keys=keys_list, resellers=resellers_list, current_user=current_user, current_username=current_user, current_role=current_role)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/v", methods=["POST", "GET"])
def verify():
    json_data = request.get_json(silent=True) or {}
    form_data = request.form or {}
    args_data = request.args or {}
    values_data = request.values or {}

    req_type = (json_data.get("type") or form_data.get("type") or args_data.get("type") or values_data.get("type") or "").strip()
    key = (
        json_data.get("key") or form_data.get("key") or args_data.get("key") or values_data.get("key") or
        json_data.get("username") or form_data.get("username") or args_data.get("username") or values_data.get("username") or
        json_data.get("license") or form_data.get("license") or args_data.get("license") or values_data.get("license") or ""
    ).strip()

    device_id = (
        json_data.get("device_id") or form_data.get("device_id") or args_data.get("device_id") or values_data.get("device_id") or
        json_data.get("hwid") or form_data.get("hwid") or args_data.get("hwid") or values_data.get("hwid") or "unknown_device"
    ).strip()

    response_panel_07 = {
        "success": True, 
        "code": 68, 
        "message": "Initialized",
        "sessionid": uuid.uuid4().hex,
        "appinfo": {
            "numUsers": "N/A",
            "numOnlineUsers": "N/A",
            "numKeys": "N/A",
            "version": "1.0",
            "customerPanelLink": "https://keyauth.cc/panel/modderstrick/07team/"
        },
        "newSession": True,
        "nonce": uuid.uuid4().hex,
        "ownerid": "Ug7ojMSG2K"
    }

    if req_type == "init":
        return jsonify(response_panel_07)

    if not key:
        return jsonify({"code": 400, "message": "missing_parameters", "success": False})

    conn = get_db_connection()
    row = conn.execute("SELECT max_devices, devices_list, expiry_date, status, panel_name FROM keys WHERE [key] = ?", (key,)).fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Invalid key or not registered!"})

    if row['status'] == "banned":
        conn.close()
        return jsonify({"success": False, "message": "banned"})

    try:
        expiry_dt = datetime.strptime(row['expiry_date'], '%Y-%m-%d %H:%M:%S')
    except:
        conn.close()
        return jsonify({"success": False, "message": "date_error"})

    if datetime.now() > expiry_dt:
        conn.close()
        return jsonify({"success": False, "message": "expired"})

    devices = [d for d in (row['devices_list'] or "").split(",") if d]
    if device_id in devices or len(devices) < row['max_devices']:
        if device_id not in devices and device_id != "unknown_device":
            devices.append(device_id)
            conn.execute("UPDATE keys SET devices_list = ? WHERE [key] = ?", (",".join(devices), key))
            conn.commit()
        conn.close()
        
        if "Panel 07" in row['panel_name']:
            return jsonify(response_panel_07)
        else:
            return jsonify({
                "success": True, 
                "message": f"Authenticated successfully via {row['panel_name']}",
                "expiry": row['expiry_date']
            })

    conn.close()
    return jsonify({"success": False, "message": "limit_reached"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    