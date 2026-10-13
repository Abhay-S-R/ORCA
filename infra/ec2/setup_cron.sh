#!/usr/bin/env bash
# ==============================================================================
# Setup Cron on AWS EC2 Host for ORCA Data Ingestion
#
# Usage on EC2:
#   chmod +x setup_cron.sh
#   ./setup_cron.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_FILE="${SCRIPT_DIR}/crontab.txt"

echo "=== Verifying Docker Container ==="
if ! docker ps | grep -q "orca-backend"; then
    echo "[ERROR] 'orca-backend' container is not running!"
    echo "Please ensure the container is running first: docker ps"
    exit 1
fi
echo "[OK] 'orca-backend' container is running."

echo "=== Verifying Host Data Directory ==="
HOST_DATA_DIR="/home/ec2-user/orca_data"
if [ ! -d "$HOST_DATA_DIR" ]; then
    echo "[INFO] Creating ${HOST_DATA_DIR}..."
    mkdir -p "$HOST_DATA_DIR"
fi
echo "[OK] Host data directory exists at ${HOST_DATA_DIR}."

echo "=== Installing Crontab for $(whoami) ==="
# Append jobs without duplicating existing ORCA jobs
crontab -l 2>/dev/null | grep -v "orca-backend" > /tmp/current_crontab || true
cat "$CRON_FILE" >> /tmp/current_crontab
crontab /tmp/current_crontab
rm /tmp/current_crontab

echo "[SUCCESS] Crontab updated successfully! Current schedule:"
crontab -l | grep "orca-backend"

echo ""
echo "=== Testing Refresh Scripts inside Container ==="
echo "You can manually trigger a test refresh at any time using:"
echo "  docker exec -e PYTHONIOENCODING=utf-8 orca-backend /bin/sh /scripts/cron_refresh.sh"
echo "  docker exec -e PYTHONIOENCODING=utf-8 orca-backend python -m orca.data.freshness"
