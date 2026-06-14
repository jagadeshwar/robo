import os

# Serial port to Arduino (check with: ls /dev/ttyUSB* or ls /dev/ttyACM*)
ARDUINO_PORT     = os.getenv("ARDUINO_PORT", "/dev/ttyACM1")
ARDUINO_BAUDRATE = 115200

# Sensor thresholds
MOISTURE_DRY_PCT   = 30   # % — below this, irrigation needed
MOISTURE_WET_PCT   = 70   # % — above this, gate closes
NPK_N_LOW_THRESHOLD = 20  # mg/kg
NPK_P_LOW_THRESHOLD = 10
NPK_K_LOW_THRESHOLD = 15

# Gate logic: auto-open when average moisture < MOISTURE_DRY_PCT
GATE_AUTO_CONTROL  = False

# Motion defaults used when UI commands omit speed or duration
DEFAULT_MOVE_SPEED = 180
DEFAULT_TURN_SPEED = 160

# ── Autonomous navigation (open-loop, time-based dead reckoning) ──────────────
# The robot has no wheel encoders/GPS, so coverage distance & turn angle are
# derived from time. CALIBRATE these two values for accurate field coverage:
#   1. Send FORWARD at NAV_MOVE_SPEED, time how long to travel a known distance,
#      then set NAV_FORWARD_CM_PER_SEC = distance_cm / seconds.
#   2. Send LEFT/RIGHT at NAV_TURN_SPEED, time a full 90° pivot,
#      then set NAV_TURN_90_SEC = that time in seconds.
NAV_MOVE_SPEED         = 180    # PWM 0-255 used while driving rows
NAV_TURN_SPEED         = 160    # PWM 0-255 used while pivoting
NAV_FORWARD_CM_PER_SEC = 20.0   # ground speed at NAV_MOVE_SPEED (MEASURE THIS)
NAV_TURN_90_SEC        = 1.0    # seconds for a 90° pivot at NAV_TURN_SPEED (MEASURE THIS)

# Spray: auto-spray when disease or low NPK detected
SPRAY_DURATION_SEC = 5    # seconds per spray cycle

# Image upload settings
UPLOAD_FOLDER      = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "webp"}
MAX_CONTENT_MB     = 10

# Plant disease model (TensorFlow Lite)
MODEL_PATH         = os.path.join(os.path.dirname(__file__), "vision", "models", "plant_disease.tflite")
LABELS_PATH        = os.path.join(os.path.dirname(__file__), "vision", "models", "labels.txt")
IMG_SIZE           = (224, 224)      # model input size
DISEASE_CONFIDENCE = 0.65            # min confidence to flag as diseased

# Flask dashboard
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
SECRET_KEY = os.getenv("SECRET_KEY", "farmrobo-dev-key-change-in-prod")

# Logging
LOG_FILE   = os.path.join(os.path.dirname(__file__), "logs", "farmrobo.log")
LOG_LEVEL  = "INFO"
