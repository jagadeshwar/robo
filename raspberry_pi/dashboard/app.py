"""
Flask + SocketIO dashboard for FarmRobo.
Motor commands use WebSocket for real-time low-latency control.
Everything else (state, upload, history) stays on HTTP.
"""

import logging
import os
import sys
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from robot.controller import RobotController

# ── logging ───────────────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
_handlers = [logging.FileHandler(config.LOG_FILE)]
if sys.stdout.isatty():
    _handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── app + socketio ─────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates", static_folder="templates/static")
app.secret_key = config.SECRET_KEY
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*", logger=False, engineio_logger=False)

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
_analysis_history: list = []

robot = RobotController()


def _allowed_file(filename: str) -> bool:
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS


# ── WebSocket motor control (real-time) ───────────────────────────────────────

_MOTOR_ACTIONS = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}
_ALL_ALLOWED   = _MOTOR_ACTIONS | {"SPRAY", "SPRAY_ON", "SPRAY_OFF",
                                    "WEED", "WEED_ON", "WEED_OFF",
                                    "GATE_OPEN", "GATE_CLOSE"}

@socketio.on('motor')
def ws_motor(data):
    action = str(data.get('action', '')).upper()
    speed  = data.get('speed', None)
    params = {'speed': speed} if speed else {}
    if action in _MOTOR_ACTIONS:
        robot.command(action, params)

@socketio.on('connect')
def ws_connect():
    logger.debug("WebSocket client connected")

@socketio.on('disconnect')
def ws_disconnect():
    robot.command('STOP', {})
    logger.debug("WebSocket client disconnected — motors stopped")


# ── HTTP routes (non-motor) ───────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(robot.get_state())


@app.route("/api/command", methods=["POST"])
def api_command():
    body   = request.get_json(force=True, silent=True) or {}
    action = body.get("action", "").upper()
    params = body.get("params", {})
    if action not in _ALL_ALLOWED:
        return jsonify({"ok": False, "error": f"Unknown action: {action}"}), 400
    try:
        robot.command(action, params)
        return jsonify({"ok": True, "action": action})
    except Exception as e:
        logger.exception("Error handling command %s", action)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "No image field"}), 400
    file = request.files["image"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "Empty filename"}), 400
    if not _allowed_file(file.filename):
        return jsonify({"ok": False, "error": "File type not allowed"}), 415
    ext      = Path(secure_filename(file.filename)).suffix.lower()
    unique   = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = os.path.join(config.UPLOAD_FOLDER, unique)
    file.save(save_path)
    result = robot.analyze_image(save_path)
    result["image_url"] = f"/uploads/{unique}"
    result["timestamp"] = int(time.time())
    _analysis_history.insert(0, result)
    if len(_analysis_history) > 50:
        _analysis_history.pop()
    return jsonify({"ok": True, "result": result})


@app.route("/api/history")
def api_history():
    n = min(int(request.args.get("n", 10)), 50)
    return jsonify(_analysis_history[:n])


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(config.UPLOAD_FOLDER, filename)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting FarmRobo dashboard on %s:%d", config.FLASK_HOST, config.FLASK_PORT)
    robot.start()
    try:
        socketio.run(app, host=config.FLASK_HOST, port=config.FLASK_PORT,
                     debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
    finally:
        robot.stop()
