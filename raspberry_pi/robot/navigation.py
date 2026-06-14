"""
Autonomous field navigation for FarmRobo.

The robot has differential drive (left/right wheels) and a single front
ultrasonic sensor — no wheel encoders, GPS or IMU. So coverage is done with
**open-loop, time-based dead reckoning**: distances and turn angles are
converted to drive durations using calibrated constants in config.py.

Pattern: boustrophedon ("lawnmower"/snake) coverage of a rectangular field.
  row 1:  ───────────────►
                          │  (turn, shift one row spacing, turn)
  row 2:  ◄───────────────
          │
  row 3:  ───────────────►
  ...

The front ultrasonic sensor pauses driving while an obstacle is within range
and resumes automatically once it clears. A manual motor command or NAV_STOP
cancels the run immediately.

NOTE: accuracy depends entirely on calibrating NAV_FORWARD_CM_PER_SEC and
NAV_TURN_90_SEC for your robot — see config.py.
"""

import logging
import math
import threading
import time

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

logger = logging.getLogger(__name__)


class NavigationController:
    def __init__(self, controller):
        self._ctrl   = controller          # RobotController (for arduino + state)
        self._thread = None
        self._stop   = threading.Event()
        self._lock   = threading.Lock()
        self._status = "idle"
        self._row    = 0
        self._rows   = 0

    @property
    def arduino(self):
        return self._ctrl.arduino

    # ── public API ───────────────────────────────────────────────────────────

    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status_dict(self) -> dict:
        with self._lock:
            return {
                "active": self.is_active(),
                "status": self._status,
                "row":    self._row,
                "rows":   self._rows,
            }

    def start(self, params: dict) -> bool:
        """Begin autonomous coverage. params: length_m, width_m, row_spacing_m, speed."""
        if self.is_active():
            logger.warning("Navigation already running — ignoring start")
            return False
        try:
            length_m  = float(params.get("length_m", 0))
            width_m   = float(params.get("width_m", 0))
            spacing_m = float(params.get("row_spacing_m", 0))
        except (TypeError, ValueError):
            logger.error("Navigation start: invalid numeric params %s", params)
            return False

        if length_m <= 0 or width_m <= 0 or spacing_m <= 0:
            logger.error("Navigation start: length/width/spacing must be > 0")
            return False

        try:
            speed = int(params.get("speed") or config.NAV_MOVE_SPEED)
        except (TypeError, ValueError):
            speed = config.NAV_MOVE_SPEED
        speed = max(1, min(255, speed))

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(length_m, width_m, spacing_m, speed),
            daemon=True,
        )
        self._thread.start()
        logger.info("Navigation started: %.1fm x %.1fm, row spacing %.2fm, speed %d",
                    length_m, width_m, spacing_m, speed)
        return True

    def cancel(self):
        """Stop the run as soon as possible. Safe to call when not running."""
        if self.is_active():
            logger.info("Navigation cancelled")
            self._stop.set()
        self.arduino.stop()

    # ── coverage plan ────────────────────────────────────────────────────────

    def _run(self, length_m, width_m, spacing_m, speed):
        length_cm  = length_m * 100.0
        spacing_cm = spacing_m * 100.0
        rows       = max(1, int(round(width_m / spacing_m)))

        with self._lock:
            self._rows   = rows
            self._row    = 0
            self._status = "running"

        logger.info("Coverage plan: %d rows of %.0f cm, %.0f cm apart",
                    rows, length_cm, spacing_cm)

        try:
            for i in range(rows):
                if self._stop.is_set():
                    break
                with self._lock:
                    self._row = i + 1
                    self._status = "running: row %d/%d" % (i + 1, rows)

                # Drive the length of the row.
                if not self._drive_forward(length_cm, speed):
                    break
                if i == rows - 1:
                    break  # last row — no transition needed

                # Transition to the next row: turn, shift one spacing, turn.
                # Alternate turn direction so the path snakes back and forth.
                turn = self._turn_right if (i % 2 == 0) else self._turn_left
                if not turn(90):
                    break
                if not self._drive_forward(spacing_cm, speed):
                    break
                if not turn(90):
                    break
        finally:
            self.arduino.stop()
            with self._lock:
                if self._stop.is_set():
                    self._status = "stopped"
                else:
                    self._status = "complete"
                self._row = 0
            logger.info("Navigation finished: %s", self._status)

    # ── primitive moves (interruptible, obstacle-aware) ──────────────────────

    def _drive_forward(self, distance_cm, speed) -> bool:
        if distance_cm <= 0:
            return True
        duration = distance_cm / max(0.1, config.NAV_FORWARD_CM_PER_SEC)
        return self._run_motion(lambda: self.arduino.forward(speed),
                                duration, obstacle_aware=True)

    def _turn_left(self, degrees) -> bool:
        duration = (degrees / 90.0) * config.NAV_TURN_90_SEC
        return self._run_motion(lambda: self.arduino.turn_left(config.NAV_TURN_SPEED),
                                duration, obstacle_aware=False)

    def _turn_right(self, degrees) -> bool:
        duration = (degrees / 90.0) * config.NAV_TURN_90_SEC
        return self._run_motion(lambda: self.arduino.turn_right(config.NAV_TURN_SPEED),
                                duration, obstacle_aware=False)

    def _run_motion(self, motion_fn, duration, obstacle_aware) -> bool:
        """Run motion_fn for `duration` seconds. Returns True if it completed,
        False if cancelled. Pauses (not counting time) while an obstacle is
        seen, if obstacle_aware."""
        motion_fn()
        remaining = duration
        last = time.time()
        while remaining > 0:
            if self._stop.is_set():
                self.arduino.stop()
                return False

            if obstacle_aware and self._obstacle():
                self.arduino.stop()
                with self._lock:
                    self._status = "paused: obstacle ahead"
                # wait for the path to clear (or cancellation)
                while self._obstacle() and not self._stop.is_set():
                    time.sleep(0.2)
                if self._stop.is_set():
                    self.arduino.stop()
                    return False
                motion_fn()  # resume
                with self._lock:
                    self._status = "running: row %d/%d" % (self._row, self._rows)
                last = time.time()
                continue

            time.sleep(0.05)
            now = time.time()
            remaining -= (now - last)
            last = now

        self.arduino.stop()
        return True

    def _obstacle(self) -> bool:
        return bool(self._ctrl.get_state().get("obstacle"))
