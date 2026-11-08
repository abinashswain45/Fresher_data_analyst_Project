# Includes Chromium + all system deps for Playwright.
FROM mcr.microsoft.com/playwright/python:v1.64.0-noble
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install chromium
COPY app ./app
RUN useradd -m applypilot && mkdir -p /data/storage && chown -R applypilot /data /app
USER applypilot
ENV STORAGE_DIR=/data/storage
EXPOSE 8000
# Single worker: browser sessions live in-process.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"]
