@echo off
REM scripts/deploy_data.cmd — Builds and deploys Render Docker image with fresh data/
REM Can be called manually or automatically at the end of refresh_daily / refresh_weekly.

cd /d "%~dp0.."

echo ========================================================
echo   ORCA: Packaging & Deploying Fresh Data to Render
echo ========================================================

REM 1. Verify Docker is running
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] Docker Desktop is not running or not responsive.
    echo Skipping Docker build and push. You can run scripts\deploy_data.cmd
    echo manually after launching Docker Desktop.
    exit /b 0
)

REM 2. Build images
echo [1/3] Building backend base image...
docker build -t orca-backend backend || (
    echo [ERROR] Failed to build orca-backend base image.
    exit /b 1
)

echo [2/3] Building Render image with fresh data/...
docker build -f infra/render/Dockerfile -t asrsyshash/orca-backend:render -t asrsyshash/orca-backend:data-base . || (
    echo [ERROR] Failed to build asrsyshash/orca-backend images.
    exit /b 1
)

REM 3. Push to Docker Hub
echo [3/3] Pushing images to Docker Hub...
docker push asrsyshash/orca-backend:data-base || (
    echo [ERROR] Failed to push data-base image to Docker Hub.
    exit /b 1
)
docker push asrsyshash/orca-backend:render || (
    echo [ERROR] Failed to push render image to Docker Hub. Ensure you are logged in via 'docker login'.
    exit /b 1
)

REM 4. Trigger Render Deploy Hook
set HOOK=
if exist backend\.venv\Scripts\python.exe (
    for /f "delims=" %%I in ('backend\.venv\Scripts\python.exe -c "import os; from pathlib import Path; p = Path('.env'); lines = p.read_text().splitlines() if p.exists() else []; env = dict(l.split('=', 1) for l in lines if '=' in l and not l.strip().startswith('#')); print(os.getenv('RENDER_DEPLOY_HOOK') or env.get('RENDER_DEPLOY_HOOK') or env.get('RENDER_DEPLOY_HOOK_URL') or '')"') do set HOOK=%%I
)

if not "%HOOK%"=="" (
    echo Triggering Render redeploy hook...
    curl -sS -X POST "%HOOK%"
    echo.
    echo [SUCCESS] Render deploy triggered successfully!
) else (
    echo [NOTE] RENDER_DEPLOY_HOOK not found in .env or environment.
    echo If you want automatic redeployment, add RENDER_DEPLOY_HOOK=https://... to your .env file.
)

echo ========================================================
echo   Done! Fresh data deployment finished.
echo ========================================================
