"""
Serial communication layer between Raspberry Pi and Arduino.
Sends JSON command lines; parses incoming JSON sensor reports.
"""
import json
import logging
import threading
import time
from typing import Callable, Optional

try:
    import serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

logger = logging.getLogger(__name__)


class ArduinoComm:
    def __init__(self, sensor_callback: Optional[Callable] = None):
        self._port       = config.ARDUINO_PORT
        self._baud       = config.ARDUINO_BAUDRATE
        self._ser: Optional[serial.Serial] = None
        self._lock       = threading.Lock()
        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self.on_sensors  = sensor_callback   # called with dict when sensors arrive
        self.latest      = {}                # most recent sensor snapshot

    # ── connection ─────────────────────────────────────────────────────────────

    def _detect_port(self) -> str:
        """Return first available ttyACM* or ttyUSB* port, or the configured default."""
        import glob
        for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
            ports = sorted(glob.glob(pattern))
            if ports:
                logger.info("Auto-detected Arduino port: %s", ports[0])
                return ports[0]
        return self._port

    def connect(self, retries: int = 5) -> bool:
        if not _SERIAL_AVAILABLE:
            logger.warning("pyserial not installed — running without Arduino")
            return False
        port = self._detect_port()
        for attempt in range(retries):
            try:
                self._ser = serial.Serial(
                    port, self._baud,
                    timeout=1, write_timeout=2
                )
                time.sleep(2)           # let Arduino reset after DTR
                self._running = True
                self._thread  = threading.Thread(target=self._reader, daemon=True)
                self._thread.start()
                logger.info("Arduino connected on %s", port)
                return True
            except (serial.SerialException, OSError) as e:
                logger.warning("Connect attempt %d failed: %s", attempt + 1, e)
                time.sleep(2)
        logger.error("Could not open Arduino serial port %s", port)
        return False

    def disconnect(self):
        self._running = False
        if self._ser and self._ser.is_open:
            self._ser.close()
        logger.info("Arduino disconnected")

    # ── reader thread ──────────────────────────────────────────────────────────

    def _reader(self):
        while self._running:
            if not self._ser or not self._ser.is_open:
                time.sleep(1)
                continue
            try:
                raw = self._ser.readline().decode("utf-8", errors="ignore").strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("Non-JSON from Arduino: %s", raw)
                    continue

                msg_type = data.get("type", "")
                if msg_type == "SENSORS":
                    self.latest = data.get("data", {})
                    if self.on_sensors:
                        self.on_sensors(self.latest)
                elif msg_type == "READY":
                    logger.info("Arduino ready: %s", data.get("msg"))
                elif msg_type == "PONG":
                    logger.debug("Arduino pong received")
                else:
                    logger.debug("Arduino msg: %s", data)
            except Exception as e:
                if self._running:
                    logger.warning("Serial read error — reconnecting: %s", e)
                    try:
                        if self._ser:
                            self._ser.close()
                    except Exception:
                        pass
                    self._ser = None
                    time.sleep(3)
                    self._detect_and_reconnect()

    def _detect_and_reconnect(self):
        port = self._detect_port()
        try:
            self._ser = serial.Serial(port, self._baud, timeout=1, write_timeout=2)
            time.sleep(2)
            logger.info("Arduino reconnected on %s", port)
        except (serial.SerialException, OSError) as e:
            logger.warning("Reconnect failed: %s", e)
            self._ser = None

    # ── command senders ────────────────────────────────────────────────────────

    def _send(self, cmd: str, val: int = 0):
        if not _SERIAL_AVAILABLE or not self._ser or not self._ser.is_open:
            logger.warning("Serial not open, command dropped: %s", cmd)
            return
        payload = json.dumps({"cmd": cmd, "val": val}) + "\n"
        logger.debug("Sending to Arduino: %s", payload.strip())
        with self._lock:
            try:
                self._ser.write(payload.encode())
            except serial.SerialException as e:
                logger.error("Send error: %s", e)

    def forward(self, speed: int = 0):  self._send("FORWARD", speed)
    def backward(self, speed: int = 0): self._send("BACKWARD", speed)
    def turn_left(self, speed: int = 0):  self._send("LEFT", speed)
    def turn_right(self, speed: int = 0): self._send("RIGHT", speed)
    def stop(self):                     self._send("STOP")
    def set_speed(self, speed: int):    self._send("SPEED", speed)

    def spray_on(self):                 self._send("SPRAY_ON")
    def spray_off(self):                self._send("SPRAY_OFF")
    def weed_on(self):                  self._send("WEED_ON")
    def weed_off(self):                 self._send("WEED_OFF")

    def gate_open(self):                self._send("GATE_OPEN")
    def gate_close(self):               self._send("GATE_CLOSE")
    def ping(self):                     self._send("PING")

    # ── convenience ────────────────────────────────────────────────────────────

    def spray_for(self, seconds: float):
        """Spray for a fixed duration then stop."""
        self.spray_on()
        time.sleep(seconds)
        self.spray_off()

    def weed_for(self, seconds: float):
        self.weed_on()
        time.sleep(seconds)
        self.weed_off()
