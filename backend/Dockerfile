# EduRag backend — production image
#
# Build:    docker build -t edurag-backend .
# Run:      docker run --rm -p 8000:8000 --env-file .env edurag-backend
#
# This is a multi-stage build. The first stage installs build
# dependencies (none currently — PyMuPDF and friends ship pure
# Python wheels); the second stage is the runtime. Slim base
# image keeps it under 400 MB.

FROM python:3.11-slim AS runtime

# System deps for PyMuPDF + Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache-friendly: this layer only
# re-builds when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source
COPY . .

# uvicorn listens on 8000 by default. Railway injects a dynamic
# $PORT, so we read it (defaulting to 8000 for local docker-compose).
EXPOSE 8000

# Single worker is fine for the dev workflow. For prod scale,
# use gunicorn + uvicorn workers or run multiple replicas behind
# a load balancer.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
