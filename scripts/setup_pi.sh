#!/usr/bin/env bash
# Run this script once on the Raspberry Pi 5 to install all dependencies.
#
#   chmod +x scripts/setup_pi.sh
#   ./scripts/setup_pi.sh

set -e

echo "=== FarmRobo Pi Setup ==="

# System packages
sudo apt-get update -y
sudo apt-get install -y \
    python3-pip python3-venv \
    libopencv-dev python3-opencv \
    libatlas-base-dev \
    libhdf5-dev \
    libjpeg-dev libpng-dev \
    git

# Create Python venv
python3 -m venv ~/farmrobo-env
source ~/farmrobo-env/bin/activate

# Install Python packages
pip install --upgrade pip
pip install -r raspberry_pi/requirements.txt

# Add user to dialout for serial access
sudo usermod -aG dialout "$USER"

# Download TFLite model + labels
python raspberry_pi/vision/download_model.py

# Create systemd service so dashboard starts on boot
SERVICE_FILE=/etc/systemd/system/farmrobo.service
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=FarmRobo Dashboard
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$HOME/farmrobo-env/bin/python raspberry_pi/dashboard/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable farmrobo
sudo systemctl start farmrobo

echo ""
echo "=== Setup complete ==="
echo "Dashboard available at: http://$(hostname -I | awk '{print $1}'):5000"
echo "Logs: journalctl -u farmrobo -f"
echo ""
echo "NOTE: Log out and back in for serial port group change to take effect."
