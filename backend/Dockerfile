FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# ponytail: split runtime from dev/CI deps if the image size becomes a problem;
# one file is fine while the backend is this small.
RUN pip install --no-cache-dir -r requirements.txt

COPY orca ./orca

EXPOSE 8000
CMD ["uvicorn", "orca.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
