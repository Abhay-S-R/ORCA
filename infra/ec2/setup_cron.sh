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
echo "=== Checking Host Swap Space ==="
if [ -f /proc/swaps ] && [ "$(wc -l < /proc/swaps)" -le 1 ]; then
    echo "[WARN] No swap space configured on EC2 host!"
    echo "       Raster tile generation can exceed 1.5 GB RAM and get OOM-killed (exit 137)."
    echo "       Recommended: add a 2GB swapfile:"
    echo "         sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
else
    echo "[OK] Swap space is active."
fi

echo ""
echo "=== Testing Refresh Scripts inside Container ==="
echo "You can manually trigger a test refresh at any time using:"
echo "  docker exec -e PYTHONIOENCODING=utf-8 orca-backend /bin/bash /scripts/cron_refresh.sh"
echo "  docker exec -e PYTHONIOENCODING=utf-8 orca-backend python -m orca.data.freshness"
