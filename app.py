<<<<<<< HEAD
from flask import Flask, render_template, jsonify, request, send_file
import platform
import psutil
import uuid
import subprocess
import json
import csv
import io
import mysql.connector

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="raquel_pm_db"
    )

def get_storage_specifications():
    storage = {
        "ssd_storage": "N/A", "ssd_serial": "N/A",
        "hdd_storage": "N/A", "hdd_serial": "N/A"
    }
    if platform.system() != "Windows":
        return storage

    try:
        # Request native drive metrics via PowerShell
        ps_cmd = 'powershell -Command "Get-PhysicalDisk | Select-Object MediaType, Size, SerialNumber | ConvertTo-Json"'
        output = subprocess.check_output(ps_cmd, shell=True).decode().strip()
        
        if output:
            disks = json.loads(output)
            # If there is only 1 drive, convert the single object into a list
            if isinstance(disks, dict):
                disks = [disks]
                
            for disk in disks:
                media_type = str(disk.get("MediaType", "")).upper()
                raw_size = disk.get("Size", 0)
                serial = str(disk.get("SerialNumber", "")).strip()
                
                if raw_size:
                    gb_size = round(int(raw_size) / (1024**3), 0)
                    size_str = f"{int(gb_size)} GB" if gb_size < 900 else f"{round(gb_size/1024, 1)} TB"
                else:
                    size_str = "N/A"

                if "SSD" in media_type:
                    storage["ssd_storage"] = size_str
                    storage["ssd_serial"] = serial if serial else "N/A"
                elif "HDD" in media_type:
                    storage["hdd_storage"] = size_str
                    storage["hdd_serial"] = serial if serial else "N/A"
                else:
                    if storage["ssd_storage"] == "N/A":
                        storage["ssd_storage"] = size_str
                        storage["ssd_serial"] = serial
                    else:
                        storage["hdd_storage"] = size_str
                        storage["hdd_serial"] = serial
    except Exception:
        pass
    return storage

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/detect", methods=["GET"])
def detect_hardware():
    try:
        total_ram = round(psutil.virtual_memory().total / (1024**3))
        ram_str = f"{total_ram} GB"
        
        is_laptop = psutil.sensors_battery() is not None
        system_unit = "Laptop" if is_laptop else "CPU"
        
        os_version = f"{platform.system()} {platform.release()}"
        if platform.system() == "Windows":
            try:
                cmd = "wmic os get Caption /value"
                out = subprocess.check_output(cmd, shell=True).decode().strip()
                if "Caption=" in out:
                    os_version = out.split("Caption=")[1].strip()
            except:
                pass

        storage = get_storage_specifications()
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 8*6, 8)][::-1]).upper()

        return jsonify({
            "success": True,
            "system_unit": system_unit,
            "it_code": platform.node(),
            "windows_edition": os_version,
            "ram_storage": ram_str,
            "ssd_storage": storage["ssd_storage"],
            "ssd_serial": storage["ssd_serial"],
            "hdd_storage": storage["hdd_storage"],
            "hdd_serial": storage["hdd_serial"],
            "mac_address": mac
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/save", methods=["POST"])
def save_entry():
    conn = None
    cursor = None
    try:
        # Support both JSON payload and standard form data
        if request.is_json:
            data = request.json
        else:
            data = request.form

        it_code = data.get("it_code", "").strip()
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. SERVER-SIDE DUPLICATE INTERCEPTION
        if it_code:
            cursor.execute("SELECT employee_name, business_name FROM specs_log WHERE it_code = %s", (it_code,))
            duplicate_record = cursor.fetchone()
            
            if duplicate_record:
                return jsonify({
                    "success": False, 
                    "error": f"DUPLICATE BLOCKED: The Device Name '{it_code}' is already registered under {duplicate_record['employee_name']} ({duplicate_record['business_name']})."
                }), 400

        # 2. PROCEED TO SAVE IF UNIQUE
        sql = """
            INSERT INTO specs_log (
                business_name, system_unit, issued_owned, employee_name, date_visited, it_code, model_brand,
                windows_edition, ram_storage, ssd_storage, ssd_serial, hdd_storage, hdd_serial,
                description_specs, date_issued, unit_age, depreciation_date, findings, fa_number,
                monitor_fa, keyboard_fa, mouse_fa, printer_fa, router_fa, webcam_fa, ups_fa,
                mac_address, action_taken, remarks, tech_support
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data.get("business_name") or data.get("issued_company_owned"), # Support both potential UI field labels
            data.get("system_unit"), 
            data.get("issued_owned") or data.get("issued_company_owned"),
            data.get("employee_name"),
            data.get("date_visited") or None, 
            it_code, 
            data.get("model_brand", ""), 
            data.get("windows_edition"),
            data.get("ram_storage") or data.get("ram_capacity"), 
            data.get("ssd_storage") or data.get("ssd_capacity"), 
            data.get("ssd_serial"), 
            data.get("hdd_storage") or data.get("hdd_capacity"), 
            data.get("hdd_serial"),
            data.get("description_specs") or data.get("processor_specs", ""), 
            data.get("date_issued") or None, 
            data.get("unit_age"), 
            data.get("depreciation_date") or None,
            data.get("findings"), 
            data.get("fa_number") or data.get("fa_system_unit"), 
            data.get("monitor_fa") or data.get("fa_monitor"), 
            data.get("keyboard_fa") or data.get("fa_keyboard"), 
            data.get("mouse_fa") or data.get("fa_mouse"), 
            data.get("printer_fa") or data.get("fa_printer"), 
            data.get("router_fa") or data.get("fa_router"), 
            data.get("webcam_fa") or data.get("fa_webcam"), 
            data.get("ups_fa") or data.get("fa_ups"),
            data.get("mac_address"), 
            data.get("action_taken"), 
            data.get("remarks"), 
            data.get("tech_support")
        )
        
        cursor.execute(sql, params)
        conn.commit()
        return jsonify({"success": True, "message": "Log stored cleanly inside MySQL!"})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/export", methods=["GET"])
def export_csv():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT business_name, system_unit, issued_owned, employee_name, date_visited, it_code, model_brand,
                   windows_edition, ram_storage, ssd_storage, ssd_serial, hdd_storage, hdd_serial, description_specs,
                   date_issued, unit_age, depreciation_date, findings, fa_number, monitor_fa, keyboard_fa, mouse_fa,
                   printer_fa, router_fa, webcam_fa, ups_fa, mac_address, action_taken, remarks, tech_support
            FROM specs_log 
            WHERE date_visited BETWEEN %s AND %s
            ORDER BY date_visited ASC
        """
        cursor.execute(sql, (start_date, end_date))
        rows = cursor.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            "Business Name", "System Unit", "Issued/Company Owned", "Employee's Name", "Date Visited", "IT Code", "Model / Brand",
            "Windows Edition", "RAM Capacity", "SSD Capacity", "SSD Serial", "HDD Capacity", "HDD Serial", "Description/Specs",
            "Date Issued", "Unit Age", "Depreciation Date", "Findings", "FA #", "Monitor FA", "Keyboard FA", "Mouse FA",
            "Printer FA", "Router FA", "Webcam FA", "UPS FA", "MAC Address", "Action Taken", "Remarks", "Tech Support"
        ])
        writer.writerows(rows)
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"Hardware_Export_{start_date}_to_{end_date}.csv"
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/check-duplicate/<it_code>', methods=['GET'])
def check_duplicate(it_code):
    """Checks if an IT Code (Device Name) already exists in the system database."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, employee_name, business_name FROM specs_log WHERE it_code = %s", (it_code,))
    exists = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if exists:
        return jsonify({
            "duplicate": True, 
            "message": f"Warning: This IT Code is already registered under {exists['employee_name']} ({exists['business_name']})."
        })
    return jsonify({"duplicate": False})

@app.route('/api/entries', methods=['GET'])
def get_entries():
    """Fetches all logged entries to populate the management log table view layout."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, date_visited, business_name, employee_name, it_code, windows_edition FROM specs_log ORDER BY id DESC")
        rows = cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    """Deletes a selected asset specification record dynamically."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM specs_log WHERE id = %s", (entry_id,))
        conn.commit()
        
        return jsonify({"success": True, "message": "Record successfully wiped out."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
=======
from flask import Flask, render_template, jsonify, request, send_file
import platform
import psutil
import uuid
import subprocess
import json
import csv
import io
import mysql.connector

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="raquel_pm_db"
    )

def get_storage_specifications():
    storage = {
        "ssd_storage": "N/A", "ssd_serial": "N/A",
        "hdd_storage": "N/A", "hdd_serial": "N/A"
    }
    if platform.system() != "Windows":
        return storage

    try:
        # Request native drive metrics via PowerShell
        ps_cmd = 'powershell -Command "Get-PhysicalDisk | Select-Object MediaType, Size, SerialNumber | ConvertTo-Json"'
        output = subprocess.check_output(ps_cmd, shell=True).decode().strip()
        
        if output:
            disks = json.loads(output)
            # If there is only 1 drive, convert the single object into a list
            if isinstance(disks, dict):
                disks = [disks]
                
            for disk in disks:
                media_type = str(disk.get("MediaType", "")).upper()
                raw_size = disk.get("Size", 0)
                serial = str(disk.get("SerialNumber", "")).strip()
                
                if raw_size:
                    gb_size = round(int(raw_size) / (1024**3), 0)
                    size_str = f"{int(gb_size)} GB" if gb_size < 900 else f"{round(gb_size/1024, 1)} TB"
                else:
                    size_str = "N/A"

                if "SSD" in media_type:
                    storage["ssd_storage"] = size_str
                    storage["ssd_serial"] = serial if serial else "N/A"
                elif "HDD" in media_type:
                    storage["hdd_storage"] = size_str
                    storage["hdd_serial"] = serial if serial else "N/A"
                else:
                    if storage["ssd_storage"] == "N/A":
                        storage["ssd_storage"] = size_str
                        storage["ssd_serial"] = serial
                    else:
                        storage["hdd_storage"] = size_str
                        storage["hdd_serial"] = serial
    except Exception:
        pass
    return storage

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/detect", methods=["GET"])
def detect_hardware():
    try:
        total_ram = round(psutil.virtual_memory().total / (1024**3))
        ram_str = f"{total_ram} GB"
        
        is_laptop = psutil.sensors_battery() is not None
        system_unit = "Laptop" if is_laptop else "CPU"
        
        os_version = f"{platform.system()} {platform.release()}"
        if platform.system() == "Windows":
            try:
                cmd = "wmic os get Caption /value"
                out = subprocess.check_output(cmd, shell=True).decode().strip()
                if "Caption=" in out:
                    os_version = out.split("Caption=")[1].strip()
            except:
                pass

        storage = get_storage_specifications()
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 8*6, 8)][::-1]).upper()

        return jsonify({
            "success": True,
            "system_unit": system_unit,
            "it_code": platform.node(),
            "windows_edition": os_version,
            "ram_storage": ram_str,
            "ssd_storage": storage["ssd_storage"],
            "ssd_serial": storage["ssd_serial"],
            "hdd_storage": storage["hdd_storage"],
            "hdd_serial": storage["hdd_serial"],
            "mac_address": mac
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/save", methods=["POST"])
def save_entry():
    conn = None
    cursor = None
    try:
        # Support both JSON payload and standard form data
        if request.is_json:
            data = request.json
        else:
            data = request.form

        it_code = data.get("it_code", "").strip()
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. SERVER-SIDE DUPLICATE INTERCEPTION
        if it_code:
            cursor.execute("SELECT employee_name, business_name FROM specs_log WHERE it_code = %s", (it_code,))
            duplicate_record = cursor.fetchone()
            
            if duplicate_record:
                return jsonify({
                    "success": False, 
                    "error": f"DUPLICATE BLOCKED: The Device Name '{it_code}' is already registered under {duplicate_record['employee_name']} ({duplicate_record['business_name']})."
                }), 400

        # 2. PROCEED TO SAVE IF UNIQUE
        sql = """
            INSERT INTO specs_log (
                business_name, system_unit, issued_owned, employee_name, date_visited, it_code, model_brand,
                windows_edition, ram_storage, ssd_storage, ssd_serial, hdd_storage, hdd_serial,
                description_specs, date_issued, unit_age, depreciation_date, findings, fa_number,
                monitor_fa, keyboard_fa, mouse_fa, printer_fa, router_fa, webcam_fa, ups_fa,
                mac_address, action_taken, remarks, tech_support
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data.get("business_name") or data.get("issued_company_owned"), # Support both potential UI field labels
            data.get("system_unit"), 
            data.get("issued_owned") or data.get("issued_company_owned"),
            data.get("employee_name"),
            data.get("date_visited") or None, 
            it_code, 
            data.get("model_brand", ""), 
            data.get("windows_edition"),
            data.get("ram_storage") or data.get("ram_capacity"), 
            data.get("ssd_storage") or data.get("ssd_capacity"), 
            data.get("ssd_serial"), 
            data.get("hdd_storage") or data.get("hdd_capacity"), 
            data.get("hdd_serial"),
            data.get("description_specs") or data.get("processor_specs", ""), 
            data.get("date_issued") or None, 
            data.get("unit_age"), 
            data.get("depreciation_date") or None,
            data.get("findings"), 
            data.get("fa_number") or data.get("fa_system_unit"), 
            data.get("monitor_fa") or data.get("fa_monitor"), 
            data.get("keyboard_fa") or data.get("fa_keyboard"), 
            data.get("mouse_fa") or data.get("fa_mouse"), 
            data.get("printer_fa") or data.get("fa_printer"), 
            data.get("router_fa") or data.get("fa_router"), 
            data.get("webcam_fa") or data.get("fa_webcam"), 
            data.get("ups_fa") or data.get("fa_ups"),
            data.get("mac_address"), 
            data.get("action_taken"), 
            data.get("remarks"), 
            data.get("tech_support")
        )
        
        cursor.execute(sql, params)
        conn.commit()
        return jsonify({"success": True, "message": "Log stored cleanly inside MySQL!"})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/export", methods=["GET"])
def export_csv():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT business_name, system_unit, issued_owned, employee_name, date_visited, it_code, model_brand,
                   windows_edition, ram_storage, ssd_storage, ssd_serial, hdd_storage, hdd_serial, description_specs,
                   date_issued, unit_age, depreciation_date, findings, fa_number, monitor_fa, keyboard_fa, mouse_fa,
                   printer_fa, router_fa, webcam_fa, ups_fa, mac_address, action_taken, remarks, tech_support
            FROM specs_log 
            WHERE date_visited BETWEEN %s AND %s
            ORDER BY date_visited ASC
        """
        cursor.execute(sql, (start_date, end_date))
        rows = cursor.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            "Business Name", "System Unit", "Issued/Company Owned", "Employee's Name", "Date Visited", "IT Code", "Model / Brand",
            "Windows Edition", "RAM Capacity", "SSD Capacity", "SSD Serial", "HDD Capacity", "HDD Serial", "Description/Specs",
            "Date Issued", "Unit Age", "Depreciation Date", "Findings", "FA #", "Monitor FA", "Keyboard FA", "Mouse FA",
            "Printer FA", "Router FA", "Webcam FA", "UPS FA", "MAC Address", "Action Taken", "Remarks", "Tech Support"
        ])
        writer.writerows(rows)
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"Hardware_Export_{start_date}_to_{end_date}.csv"
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/check-duplicate/<it_code>', methods=['GET'])
def check_duplicate(it_code):
    """Checks if an IT Code (Device Name) already exists in the system database."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, employee_name, business_name FROM specs_log WHERE it_code = %s", (it_code,))
    exists = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if exists:
        return jsonify({
            "duplicate": True, 
            "message": f"Warning: This IT Code is already registered under {exists['employee_name']} ({exists['business_name']})."
        })
    return jsonify({"duplicate": False})

@app.route('/api/entries', methods=['GET'])
def get_entries():
    """Fetches all logged entries to populate the management log table view layout."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, date_visited, business_name, employee_name, it_code, windows_edition FROM specs_log ORDER BY id DESC")
        rows = cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    """Deletes a selected asset specification record dynamically."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM specs_log WHERE id = %s", (entry_id,))
        conn.commit()
        
        return jsonify({"success": True, "message": "Record successfully wiped out."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
>>>>>>> 13a1abf13178affa7667bcddfae8e917e38afd3a
    app.run(debug=True, port=5000)