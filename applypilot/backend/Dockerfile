FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY requirements.txt .
# Python deps + Chromium and its system libraries for Playwright
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
COPY app ./app
RUN useradd -m applypilot && mkdir -p /data/storage && chown -R applypilot /data /app /ms-playwright
USER applypilot
ENV STORAGE_DIR=/data/storage
EXPOSE 8000
# Single worker: browser sessions live in-process.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"]
