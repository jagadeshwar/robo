#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Installing core dependencies ==="
pip install flask pyserial pillow numpy --quiet

echo "=== Starting FarmRobo dashboard ==="
python dashboard/app.py
