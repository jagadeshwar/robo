#!/bin/bash
# FarmRobo auto-start wrapper.
# Launched on boot via the user's crontab (@reboot). Keeps the dashboard
# running and restarts it automatically if it ever exits/crashes.

cd "$(dirname "$0")" || exit 1
mkdir -p logs

# Avoid starting a second copy if one is already running.
if pgrep -f "python3 .*dashboard/app.py" > /dev/null; then
    echo "$(date) run.sh: app already running, exiting" >> logs/run.log
    exit 0
fi

echo "$(date) run.sh: starting supervisor loop" >> logs/run.log
while true; do
    echo "$(date) run.sh: launching app" >> logs/run.log
    python3 dashboard/app.py >> logs/farmrobo.log 2>&1
    echo "$(date) run.sh: app exited (code $?), restarting in 5s" >> logs/run.log
    sleep 5
done
