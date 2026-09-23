FROM python:3.11-slim

WORKDIR /app

# IndicTransToolkit (requirements.txt) builds a Cython extension at install
# time and has no prebuilt wheel — slim has no compiler by default.
RUN apt-get update && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Pre-install CPU-only PyTorch to prevent downloading 10+ GB of CUDA wheels on Linux:
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY orca ./orca

EXPOSE 8000
CMD ["uvicorn", "orca.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
