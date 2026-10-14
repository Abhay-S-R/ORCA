FROM python:3.11-slim

WORKDIR /app

# Dependencies for Cython extensions & rasterio
RUN apt-get update && apt-get install --no-install-recommends -y build-essential libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
# Pre-install CPU-only PyTorch to prevent downloading heavy CUDA wheels on Linux:
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/orca ./orca
COPY backend/scripts ./backend/scripts
COPY scripts ./scripts

# Symlinks for backwards compatibility and data persistence:
# 1. /scripts -> /app/scripts
# 2. /app/data -> /data (mounted host volume at /home/ec2-user/orca_data)
RUN ln -s /app/scripts /scripts && \
    mkdir -p /data && \
    ln -s /data /app/data

ENV ORCA_DATA_DIR=/data
ENV PYTHONPATH=/app
ENV PYTHONIOENCODING=utf-8
ENV MALLOC_ARENA_MAX=2
ENV ORCA_LOCAL_MODELS=0

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn orca.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 3"]
