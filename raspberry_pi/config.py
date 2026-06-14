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
