#!/usr/bin/env bash
# scripts/deploy_data.sh — Builds and deploys Render Docker image with fresh data/
# Can be called manually or automatically at the end of refresh_daily / refresh_weekly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "========================================================"
echo "  ORCA: Packaging & Deploying Fresh Data to Render"
echo "========================================================"

# 1. Verify Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "[WARN] Docker daemon is not running or not responsive."
    echo "Skipping Docker build and push. You can run scripts/deploy_data.sh manually later."
    exit 0
fi

# 2. Build images
echo "[1/3] Building backend base image..."
docker build -t orca-backend backend

echo "[2/3] Building Render image with fresh data/..."
docker build -f infra/render/Dockerfile -t asrsyshash/orca-backend:render -t asrsyshash/orca-backend:data-base .

# 3. Push to Docker Hub
echo "[3/3] Pushing images to Docker Hub..."
docker push asrsyshash/orca-backend:data-base
docker push asrsyshash/orca-backend:render

# 4. Trigger Render Deploy Hook
HOOK=""
if [ -f .env ]; then
    HOOK=$(grep -E '^(RENDER_DEPLOY_HOOK|RENDER_DEPLOY_HOOK_URL)=' .env | cut -d '=' -f2- | tr -d '"'\'' ' | head -n1 || true)
fi
HOOK="${HOOK:-${RENDER_DEPLOY_HOOK:-}}"

if [ -n "$HOOK" ]; then
    echo "Triggering Render redeploy hook..."
    curl -sS -X POST "$HOOK"
    echo ""
    echo "[SUCCESS] Render deploy triggered successfully!"
else
    echo "[NOTE] RENDER_DEPLOY_HOOK not found in .env or environment."
    echo "If you want automatic redeployment, add RENDER_DEPLOY_HOOK=https://... to your .env file."
fi

echo "========================================================"
echo "  Done! Fresh data deployment finished."
echo "========================================================"
