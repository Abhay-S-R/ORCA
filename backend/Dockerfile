FROM python:3.11-slim

WORKDIR /app

# IndicTransToolkit (requirements.txt) builds a Cython extension at install
# time and has no prebuilt wheel — slim has no compiler by default. libexpat1:
# rasterio's wheel links it and slim lacks it (xarray's rasterio engine fails).
RUN apt-get update && apt-get install --no-install-recommends -y build-essential libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Pre-install CPU-only PyTorch to prevent downloading 10+ GB of CUDA wheels on Linux:
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY orca ./orca

# The agents run in parallel threads; glibc's default of up to 8 malloc arenas per
# core lets freed memory fragment across them instead of being reused.
ENV MALLOC_ARENA_MAX=2

EXPOSE 8000
# --timeout-graceful-shutdown 3 (orca_final §28, P6.12) — a query in flight
# gets 3s to finish before `docker compose down`/a redeploy kills it, short
# enough that a demo restart is not a multi-second hang either way.
# $PORT: Render (and most PaaS) tell the container which port to listen on.
CMD ["sh", "-c", "exec uvicorn orca.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 3"]
