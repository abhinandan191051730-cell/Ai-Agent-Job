#!/bin/bash
# scheduling/cron.sh
#
# Run every 4 hours during working hours (8 AM - 8 PM)
# Add to crontab via: crontab -e
#
# Example crontab entry:
#   0 */4 * * * /path/to/Ai-Agent/scheduling/cron.sh
#
# This script uses a lock file to prevent overlapping runs.

cd "$(dirname "$0")/.." || exit 1
LOCK_FILE="./data/agent.lock"
PID_FILE="./data/agent.pid"

# Check for existing lock
if [ -f "$LOCK_FILE" ]; then
    echo "$(date): Lock file exists. Another run may be in progress (PID: $(cat "$PID_FILE" 2>/dev/null || echo "unknown")). Exiting."
    exit 0
fi

# Create lock
echo $$ > "$PID_FILE"
trap 'rm -f "$LOCK_FILE" "$PID_FILE"; exit' INT TERM EXIT
touch "$LOCK_FILE"

# Activate virtual environment if using one
# source venv/bin/activate

# Run the agent
echo "$(date): Starting scheduled run"
python main.py --apply 2>&1 >> "./data/logs/cron.log"
echo "$(date): Run complete (exit code: $?)"
