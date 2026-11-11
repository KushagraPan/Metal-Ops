# Pinned Python base image
FROM python:3.11.9-slim-bookworm

# Prevent Python from writing .pyc files and buffer output
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Kolkata \
    STORAGE_DIR=/app/storage

# Install system dependencies (including tzdata for timezone configuration)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -g 1000 metalops && \
    useradd -u 1000 -g metalops -m -s /bin/sh metalops

WORKDIR /app

# Install Python dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code, migrations, seed data, and scripts
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .
COPY seed_data/ ./seed_data/
COPY scripts/entrypoint.sh ./scripts/entrypoint.sh

# Ensure storage directory exists and assign permissions to non-root user
RUN mkdir -p /app/storage && \
    chmod +x /app/scripts/entrypoint.sh && \
    chown -R metalops:metalops /app

USER metalops

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]

