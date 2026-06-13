# FarmRobo

Autonomous farm robot that detects plant diseases from uploaded photos, monitors soil moisture and nutrients, controls spraying, weed removal, and a gate — all managed from a Raspberry Pi 5 web dashboard.

## Hardware You Need

| You already have | Role |
|-----------------|------|
| Raspberry Pi 5  | Main brain — ML inference, web dashboard, serial control |
| Arduino (Mega recommended) | Low-level I/O — motors, sensors, actuators |
| L298N Motor Driver | 4-wheel drive control |
| Buck Converter(s) | Voltage regulation from battery |
| Batteries (12V) | Power source |

See **[hardware/wiring_guide.md](hardware/wiring_guide.md)** for full wiring and bill of materials.

---

## Project Structure

```
farm-robo/
├── arduino/
│   └── farm_robo/
│       └── farm_robo.ino          ← Flash this to Arduino
│
├── raspberry_pi/
│   ├── config.py                  ← All thresholds & settings
│   ├── requirements.txt
│   ├── dashboard/
│   │   ├── app.py                 ← Flask web server (run this)
│   │   └── templates/index.html   ← Dashboard UI
│   ├── robot/
│   │   └── controller.py          ← High-level robot logic
│   ├── communication/
│   │   └── serial_comm.py         ← Arduino serial protocol
│   └── vision/
│       ├── plant_detector.py      ← TFLite disease detection
│       ├── download_model.py      ← Run once to fetch model
│       └── models/                ← .tflite + labels.txt go here
│
├── scripts/
│   ├── setup_pi.sh                ← One-command Pi setup
│   └── train_model.py             ← Fine-tune model on PlantVillage
│
└── hardware/
    └── wiring_guide.md
```

---

## Quick Start

### Step 1 — Flash Arduino

1. Open `arduino/farm_robo/farm_robo.ino` in Arduino IDE
2. Select **Arduino Mega 2560** (or your board)
3. Install libraries: **DHT sensor library** (by Adafruit), **Servo** (built-in)
4. Flash. Open Serial Monitor at 115200 baud — you should see `{"type":"READY",...}`

### Step 2 — Set Up Raspberry Pi

```bash
git clone <this-repo> farm-robo
cd farm-robo
chmod +x scripts/setup_pi.sh
./scripts/setup_pi.sh
```

This installs everything and starts the dashboard service on boot.

### Step 3 — Configure

Edit `raspberry_pi/config.py`:

```python
ARDUINO_PORT = "/dev/ttyUSB0"   # check with: ls /dev/ttyUSB* /dev/ttyACM*

MOISTURE_DRY_PCT  = 30          # open gate when soil drier than 30%
MOISTURE_WET_PCT  = 70          # close gate when soil wetter than 70%
GATE_AUTO_CONTROL = True        # set False for manual-only gate

SPRAY_DURATION_SEC = 5          # seconds of spray per detected disease
DISEASE_CONFIDENCE = 0.65       # min ML confidence before spraying
```

### Step 4 — Open Dashboard

Navigate to `http://<pi-ip>:5000` from any phone or laptop on the same WiFi.

---

## How It Works

### Plant Disease Detection (Image Upload)

Since you don't have a camera module yet, upload photos from your phone:

1. Take a photo of the plant leaf
2. Open the dashboard on your phone browser
3. Tap "Click or drag & drop a plant photo"
4. The Pi runs inference and shows: plant name, disease, confidence, recommended action
5. If a disease is detected above the confidence threshold → robot automatically sprays

Supported plants: Apple, Blueberry, Cherry, Corn, Grape, Orange, Peach, Pepper, Potato, Raspberry, Soybean, Squash, Strawberry, Tomato (38 disease classes total).

### Soil Monitoring & Gate Control

The Arduino reads 3 moisture zones and an NPK sensor every 500 ms, sending JSON over serial to the Pi.

**Auto-gate logic:**
- Average moisture < 30% → gate opens (irrigation valve / entrance gate signal)
- Average moisture > 70% → gate closes
- Low NPK detected → triggers a spray cycle automatically

### Weed Detection

Currently: if the uploaded photo is classified as containing weeds, the weed cutter relay activates. Future: add a downward-facing camera module for real-time weed detection during patrol.

### Obstacle Avoidance

Three HC-SR04 ultrasonic sensors (front, left, right) feed into the Arduino. If an obstacle is detected within 30 cm, motors stop automatically and an alert appears on the dashboard.

---

## Training Your Own Model

For best accuracy, fine-tune on the PlantVillage dataset:

```bash
# On a PC or cloud GPU (not the Pi)
pip install tensorflow pillow
# Download PlantVillage from https://www.kaggle.com/datasets/emmarex/plantdisease
python scripts/train_model.py --data path/to/PlantVillage --epochs 20

# Copy the output to the Pi
scp raspberry_pi/vision/models/plant_disease.tflite pi@<pi-ip>:~/farm-robo/raspberry_pi/vision/models/
```

---

## Serial Protocol (Arduino ↔ Pi)

**Pi → Arduino** (commands, one JSON per line):
```json
{"cmd": "FORWARD",    "val": 180}
{"cmd": "SPRAY_ON",   "val": 0}
{"cmd": "GATE_OPEN",  "val": 0}
```

**Arduino → Pi** (sensor report, every 500 ms):
```json
{
  "type": "SENSORS",
  "data": {
    "moisture": [45, 38, 52],
    "npk": {"N": 18, "P": 12, "K": 20},
    "temp": 28.5,
    "humidity": 62.0,
    "dist": {"front": 120, "left": 999, "right": 85},
    "obstacle": false,
    "spray": false,
    "weed": false,
    "gate": "closed"
  }
}
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Permission denied /dev/ttyUSB0` | `sudo usermod -aG dialout $USER` then relogin |
| Dashboard shows "Offline" | Arduino not connected or wrong port in `config.py` |
| Model file not found | Run `python raspberry_pi/vision/download_model.py` |
| NPK reads all zeros | Check RS485 DE/RE pin wiring and sensor power (needs 12V) |
| Gate servo not moving | Check servo signal wire on D24 and 5V supply capacity |
| L298N motors not spinning | Verify ENA/ENB are connected (sometimes missing on clones) |
