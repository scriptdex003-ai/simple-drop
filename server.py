import eventlet
eventlet.monkey_patch() # Must be at the very top for Render/Gunicorn

from flask import Flask, render_template, request, Response, send_from_directory
from flask_socketio import SocketIO, emit
import os, qrcode, time, uuid, socket, subprocess
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'simpledrop_2026_secure'

# Updated for Render: added eventlet mode
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

UPLOAD_FOLDER = "uploads"
STATIC_FOLDER = "static"
QR_FILE = os.path.join(STATIC_FOLDER, "qr.png")

for folder in [UPLOAD_FOLDER, STATIC_FOLDER]:
    if not os.path.exists(folder): os.makedirs(folder)

active_users = {}

# This function is kept but simplified for Cloud use
def get_auto_ip():
    # On Render, we don't need to find the local IP manually
    # but we'll keep it as a fallback
    return "0.0.0.0"

@app.route("/")
def index():
    # On Render, your URL is your-app-name.onrender.com
    # We use request.host_url to get the correct live link for the QR code
    url = request.host_url
    qr = qrcode.make(url)
    qr.save(QR_FILE)
    return render_template("index.html")

@socketio.on("set_username")
def handle_set_username(data):
    username = data.get("username", "Guest")
    ua = request.headers.get("User-Agent", "").lower()
    icon = "📱" if "android" in ua or "iphone" in ua else "💻"
    active_users[request.sid] = {"sid": request.sid, "name": f"{icon} {username}"}
    emit("update_user_list", list(active_users.values()), broadcast=True)

@socketio.on("disconnect")
def handle_disconnect():
    if request.sid in active_users:
        del active_users[request.sid]
        emit("update_user_list", list(active_users.values()), broadcast=True)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    target_sid = request.form.get("target_sid")
    
    if not file or not target_sid:
        return "Missing data", 400
    
    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    file.save(os.path.join(UPLOAD_FOLDER, unique_name))
    
    # Sending signal to specific receiver
    socketio.emit("private_file_ready", {
        "filename": unique_name, 
        "display_name": filename
    }, to=target_sid)
    
    return "OK"

@app.route("/download/<path:filename>")
def download_file(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    def generate():
        if os.path.exists(path):
            with open(path, 'rb') as f: yield from f
            time.sleep(1)
            os.remove(path) # Cleanup after download
    return Response(generate(), mimetype='application/octet-stream', headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_FOLDER, filename)

@app.route("/ping")
def ping():
    """Simple health check for keep-alive services"""
    return "PONG", 200

# The local __main__ block is ignored by Render/Gunicorn
if __name__ == "__main__":
    print(f"SimpleDrop LIVE locally at: http://{get_auto_ip()}:5000")
    socketio.run(app, host="0.0.0.0", port=5000)