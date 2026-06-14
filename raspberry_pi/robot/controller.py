"""
High-level robot controller — ties together:
  - ArduinoComm   (motors, actuators, sensors)
  - PlantDetector (uploaded image analysis)
  - Gate logic    (moisture + nutrient based auto-control)
  - Action queue  (thread-safe command execution)
"""

import logging
import threading
import time
from queue import Queue, Empty
from typing import Optional

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from communication.serial_comm import ArduinoComm
from vision.plant_detector import PlantDetector

logger = logging.getLogger(__name__)


class RobotController:
    def __init__(self):
        self.arduino  = ArduinoComm(sensor_callback=self._on_sensors)
        self.detector = PlantDetector(config.MODEL_PATH, config.LABELS_PATH, config.IMG_SIZE)
        self._queue   = Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self.state    = {
            "mode":          "IDLE",        # IDLE | PATROL | MANUAL
            "sensors":       {},
            "last_analysis": None,
            "gate":          "closed",
            "spray":         False,
            "weed":          False,
            "obstacle":      False,
        }
        self._lock = threading.Lock()

    # ── lifecycle ───────────────────────────────────────────────────────────────

    def start(self) -> bool:
        connected = self.arduino.connect()
        if not connected:
            logger.warning("Arduino not connected — running in simulation mode")
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        logger.info("Robot controller started")
        return connected

    def stop(self):
        self._running = False
        self.arduino.stop()
        self.arduino.spray_off()
        self.arduino.weed_off()
        self.arduino.disconnect()
        logger.info("Robot controller stopped")

    # ── sensor callback ─────────────────────────────────────────────────────────

    def _on_sensors(self, data: dict):
        with self._lock:
            self.state["sensors"]  = data
            self.state["obstacle"] = data.get("obstacle", False)
            self.state["gate"]     = data.get("gate", "closed")
            self.state["spray"]    = data.get("spray", False)
            self.state["weed"]     = data.get("weed", False)
        # Auto-gate logic disabled — only manual commands via UI buttons

    def _auto_gate_logic(self, data: dict):
        moisture = data.get("moisture", [50, 50, 50])
        avg_moist = sum(moisture) / max(len(moisture), 1)

        npk = data.get("npk", {})
        low_nutrients = (
            npk.get("N", 99) < config.NPK_N_LOW_THRESHOLD or
            npk.get("P", 99) < config.NPK_P_LOW_THRESHOLD or
            npk.get("K", 99) < config.NPK_K_LOW_THRESHOLD
        )

        gate_state = self.state.get("gate", "closed")

        if avg_moist < config.MOISTURE_DRY_PCT and gate_state == "closed":
            logger.info("Soil dry (%.0f%%) — opening gate", avg_moist)
            self._queue.put(("GATE_OPEN", {}))
        elif avg_moist >= config.MOISTURE_WET_PCT and gate_state == "open":
            logger.info("Soil wet (%.0f%%) — closing gate", avg_moist)
            self._queue.put(("GATE_CLOSE", {}))

        if low_nutrients:
            logger.info("Low nutrients N=%s P=%s K=%s — queuing fertilizer spray",
                        npk.get("N"), npk.get("P"), npk.get("K"))
            self._queue.put(("SPRAY", {"duration": config.SPRAY_DURATION_SEC}))

    # ── image analysis (called from web route) ──────────────────────────────────

    def analyze_image(self, image_path: str) -> dict:
        result = self.detector.analyze(image_path)
        with self._lock:
            self.state["last_analysis"] = result

        action = result.get("action", "")
        logger.info("Detection result: %s (%.0f%%) → %s",
                    result.get("label"), result.get("confidence", 0) * 100, action)

        if "SPRAY" in action and result.get("confidence", 0) >= config.DISEASE_CONFIDENCE:
            self._queue.put(("SPRAY", {"duration": config.SPRAY_DURATION_SEC}))
        if "WEED" in action:
            self._queue.put(("WEED", {"duration": 3}))

        return result

    # ── action worker ────────────────────────────────────────────────────────────

    def _worker(self):
        while self._running:
            try:
                action, params = self._queue.get(timeout=1)
                self._execute(action, params)
            except Empty:
                pass
            except Exception as e:
                logger.error("Worker error: %s", e)

    def _execute(self, action: str, params: dict):
        logger.debug("Executing action: %s %s", action, params)
        # movement commands may include optional `duration` (seconds) and `speed` (0-255)
        if action == "FORWARD":
            dur = params.get("duration", 0)
            try:
                spd = int(params.get("speed") or config.DEFAULT_MOVE_SPEED)
            except Exception:
                spd = config.DEFAULT_MOVE_SPEED
            logger.debug("Action FORWARD speed=%s dur=%s", spd, dur)
            self.arduino.forward(spd)
            if dur and dur > 0:
                time.sleep(dur)
                self.arduino.stop()
        elif action == "BACKWARD":
            dur = params.get("duration", 0)
            try:
                spd = int(params.get("speed") or config.DEFAULT_MOVE_SPEED)
            except Exception:
                spd = config.DEFAULT_MOVE_SPEED
            logger.debug("Action BACKWARD speed=%s dur=%s", spd, dur)
            self.arduino.backward(spd)
            if dur and dur > 0:
                time.sleep(dur)
                self.arduino.stop()
        elif action == "LEFT":
            dur = params.get("duration", 0)
            try:
                spd = int(params.get("speed") or config.DEFAULT_TURN_SPEED)
            except Exception:
                spd = config.DEFAULT_TURN_SPEED
            logger.debug("Action LEFT speed=%s dur=%s", spd, dur)
            self.arduino.turn_left(spd)
            if dur and dur > 0:
                time.sleep(dur)
                self.arduino.stop()
        elif action == "RIGHT":
            dur = params.get("duration", 0)
            try:
                spd = int(params.get("speed") or config.DEFAULT_TURN_SPEED)
            except Exception:
                spd = config.DEFAULT_TURN_SPEED
            logger.debug("Action RIGHT speed=%s dur=%s", spd, dur)
            self.arduino.turn_right(spd)
            if dur and dur > 0:
                time.sleep(dur)
                self.arduino.stop()
        elif action == "STOP":
            # drain any queued movement commands so STOP is immediate
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except Exception:
                    break
            self.arduino.stop()
        elif action == "SPRAY_ON":
            self.arduino.spray_on()
            with self._lock:
                self.state["spray"] = True
        elif action == "SPRAY_OFF":
            self.arduino.spray_off()
            with self._lock:
                self.state["spray"] = False
        elif action == "SPRAY":
            duration = params.get("duration", config.SPRAY_DURATION_SEC)
            logger.info("Spraying for %ds", duration)
            self.arduino.spray_for(duration)
        elif action == "WEED_ON":
            self.arduino.weed_on()
            with self._lock:
                self.state["weed"] = True
        elif action == "WEED_OFF":
            self.arduino.weed_off()
            with self._lock:
                self.state["weed"] = False
        elif action == "WEED":
            duration = params.get("duration", 3)
            logger.info("Weed remover for %ds", duration)
            self.arduino.weed_for(duration)
        elif action == "GATE_OPEN":
            self.arduino.gate_open()
            with self._lock:
                self.state["gate"] = "open"
        elif action == "GATE_CLOSE":
            self.arduino.gate_close()
            with self._lock:
                self.state["gate"] = "closed"

    # ── manual command API (called from web dashboard) ──────────────────────────

    # Motor commands bypass the queue so they execute immediately with no latency
    _IMMEDIATE = {"FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"}

    def command(self, action: str, params: dict = None):
        action = action.upper()
        if action in self._IMMEDIATE:
            self._execute(action, params or {})
        else:
            self._queue.put((action, params or {}))

    def get_state(self) -> dict:
        with self._lock:
            return dict(self.state)
