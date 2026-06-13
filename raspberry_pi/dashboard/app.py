"""
Flask web dashboard for FarmRobo.
Run on Raspberry Pi 5:  python dashboard/app.py

Routes:
  GET  /              — main dashboard page
  GET  /api/state     — JSON robot state + latest sensors
  POST /api/command   — send a robot command
  POST /api/upload    — upload plant image for disease detection
  GET  /api/history   — last N analysis results
"""

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

from flask import (Flask, jsonify, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from robot.controller import RobotController

# ── logging setup ─────────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ── app setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates", static_folder="templates/static")
app.secret_key = config.SECRET_KEY

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# history of detection results (in-memory, last 50)
_analysis_history: list = []

# ── robot controller (global singleton) ───────────────────────────────────────

robot = RobotController()


def _allowed_file(filename: str) -> bool:
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS


# ── routes ────────────────────────────────────────────────────────────────────

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

    allowed = {"FORWARD","BACKWARD","LEFT","RIGHT","STOP","SPRAY","WEED",
               "GATE_OPEN","GATE_CLOSE"}
    if action not in allowed:
        return jsonify({"ok": False, "error": f"Unknown action: {action}"}), 400

    robot.command(action, params)
    return jsonify({"ok": True, "action": action})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "No image field in request"}), 400

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
        app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False, use_reloader=False)
    finally:
        robot.stop()
