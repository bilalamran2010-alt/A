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
DB_NAME = os.path.join(BASE_DIR, "final_fix.db")

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            [key] TEXT UNIQUE NOT NULL,
            max_devices INTEGER DEFAULT 1,
            devices_list TEXT DEFAULT '',
            expiry_date TEXT,
            status TEXT DEFAULT 'active',
            panel_name TEXT DEFAULT 'Panel_07',
            owner TEXT DEFAULT 'BILAL'
        )
    ''')
    
    try:
        conn.execute("ALTER TABLE keys ADD COLUMN panel_name TEXT DEFAULT 'Panel_07'")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE keys ADD COLUMN owner TEXT DEFAULT 'BILAL'")
    except sqlite3.OperationalError:
        pass

    conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'reseller',
            bound_ip TEXT DEFAULT NULL
        )
    ''')
    
    try:
        conn.execute("ALTER TABLE admins ADD COLUMN bound_ip TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

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
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()
        
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()

        conn = get_db_connection()
        user = conn.execute("SELECT role, bound_ip FROM admins WHERE username = ? AND password = ?", (username, password)).fetchone()
        
        if user:
            role, bound_ip = user
            
            if bound_ip is None or bound_ip == "":
                conn.execute("UPDATE admins SET bound_ip = ? WHERE username = ?", (client_ip, username))
                conn.commit()
            elif bound_ip != client_ip and role != "master":
                conn.execute("UPDATE admins SET bound_ip = ? WHERE username = ?", (client_ip, username))
                conn.commit()
            
            conn.close()
            session["logged_in"] = True
            session["username"] = username
            session["role"] = role
            return redirect(url_for("admin_page"))
            
        conn.close()
        flash("Oops! Bad username or password. Check your setup.")
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
        action = request.form.get("action")
        key_name = request.form.get("key_name")

        if key_name and current_role != "master":
            key_owner = conn.execute("SELECT owner FROM keys WHERE [key] = ?", (key_name,)).fetchone()
            if key_owner and key_owner[0] != current_user:
                conn.close()
                return "<h1>Hey! You can't touch this. Unauthorized.</h1>", 403

        if action == "generate":
            name = key_name.strip() if (key_name and key_name.strip() != "") else f"KEY-{uuid.uuid4().hex[:8].upper()}"
            
            days = int(request.form.get("days", 0))
            hours = int(request.form.get("hours", 0))
            minutes = int(request.form.get("minutes", 0))
            max_d = int(request.form.get("max_devices", 1))
            
            raw_panel = request.form.get("panel_name", "Panel_07")
            panel = raw_panel.split()[0] if raw_panel else "Panel_07"

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

        elif action == "edit_key":
            new_max = int(request.form.get("new_max_devices", 1))
            raw_panel = request.form.get("new_panel", "Panel_07")
            new_panel = raw_panel.split()[0] if raw_panel else "Panel_07"
            add_days = int(request.form.get("add_days", 0))
            
            if add_days > 0:
                row = conn.execute("SELECT expiry_date FROM keys WHERE [key] = ?", (key_name,)).fetchone()
                if row:
                    try:
                        current_expiry = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                        base_time = current_expiry if current_expiry > datetime.now() else datetime.now()
                        new_expiry = (base_time + timedelta(days=add_days)).strftime('%Y-%m-%d %H:%M:%S')
                        conn.execute("UPDATE keys SET max_devices = ?, panel_name = ?, expiry_date = ? WHERE [key] = ?", 
                                     (new_max, new_panel, new_expiry, key_name))
                    except:
                        pass
            else:
                conn.execute("UPDATE keys SET max_devices = ?, panel_name = ? WHERE [key] = ?", 
                             (new_max, new_panel, key_name))
            conn.commit()

        elif action == "reset_device":
            conn.execute("UPDATE keys SET devices_list = '' WHERE [key] = ?", (key_name,))
            conn.commit()

        elif action == "delete_key":
            conn.execute("DELETE FROM keys WHERE [key] = ?", (key_name,))
            conn.commit()

        elif action == "clear_all":
            if current_role == "master":
                conn.execute("DELETE FROM keys")
            else:
                conn.execute("DELETE FROM keys WHERE owner = ?", (current_user,))
            conn.commit()

        elif action == "add_reseller" and current_role == "master":
            r_user = request.form.get("reseller_username", "").strip()
            r_pass = request.form.get("reseller_password", "").strip()
            if r_user and r_pass:
                try:
                    conn.execute("INSERT INTO admins (username, password, role, bound_ip) VALUES (?, ?, 'reseller', NULL)", (r_user, r_pass))
                    conn.commit()
                except Exception as e:
                    app.logger.error(f"Error adding reseller: {e}")

        elif action == "delete_reseller" and current_role == "master":
            target_reseller = request.form.get("reseller_username")
            if target_reseller and target_reseller != current_user:
                conn.execute("DELETE FROM admins WHERE username = ? AND role = 'reseller'", (target_reseller,))
                conn.execute("DELETE FROM keys WHERE owner = ?", (target_reseller,))
                conn.commit()

        elif action == "reset_reseller_ip" and current_role == "master":
            target_reseller = request.form.get("reseller_username")
            if target_reseller:
                conn.execute("UPDATE admins SET bound_ip = NULL WHERE username = ?", (target_reseller,))
                conn.commit()

        conn.close()
        return redirect(url_for("admin_page"))

    if current_role == "master":
        rows = conn.execute("SELECT [key], max_devices, devices_list, expiry_date, panel_name, owner FROM keys").fetchall()
    else:
        rows = conn.execute("SELECT [key], max_devices, devices_list, expiry_date, panel_name, owner FROM keys WHERE owner = ?", (current_user,)).fetchall()
        
    keys_list = []
    for r in rows:
        key_name, max_dev, devices_list, expiry_str, panel_name, owner = r
        used_dev = len([d for d in (devices_list or "").split(',') if d])

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
            "duration_string": duration_string,
            "panel_name": panel_name,
            "owner": owner
        })

    resellers_list = []
    if current_role == "master":
        reseller_rows = conn.execute("SELECT username, password, bound_ip FROM admins WHERE role = 'reseller'").fetchall()
        for r_row in reseller_rows:
            r_user, r_pass, r_ip = r_row
            key_count = conn.execute("SELECT COUNT(*) FROM keys WHERE owner = ?", (r_user,)).fetchone()[0]
            resellers_list.append({
                "username": r_user,
                "password": r_pass,
                "bound_ip": r_ip or "Not Logged In Yet",
                "key_count": key_count
            })

    conn.close()
    return render_template("admin.html", keys=keys_list, resellers=resellers_list, current_user=current_user, current_role=current_role)

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

    req_type = (
        json_data.get("type") or form_data.get("type") or args_data.get("type") or values_data.get("type") or ""
    ).strip()

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

    max_devs, devices_list, expiry, status, panel_name = row
    if status == "banned":
        conn.close()
        return jsonify({"success": False, "message": "banned"})

    try:
        expiry_dt = datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S')
    except:
        conn.close()
        return jsonify({"success": False, "message": "date_error"})

    if datetime.now() > expiry_dt:
        conn.close()
        return jsonify({"success": False, "message": "expired"})

    devices = [d for d in (devices_list or "").split(",") if d]
    if device_id in devices or len(devices) < max_devs:
        if device_id not in devices and device_id != "unknown_device":
            devices.append(device_id)
            conn.execute("UPDATE keys SET devices_list = ? WHERE [key] = ?", (",".join(devices), key))
            conn.commit()
        conn.close()
        
        if panel_name == "Panel_07":
            return jsonify(response_panel_07)
        else:
            return jsonify({"success": False, "message": "updated soon"})

    conn.close()
    return jsonify({"success": False, "message": "limit_reached"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    