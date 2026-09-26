FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user — a compromised bot process must not own the container.
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/chromadb_store /app/logs /app/data \
    && chown -R appuser:appuser /app
USER appuser

# Health: API /api/health when enabled, else fall back to "bot.main alive".
# (API_ENABLED=false disables the HTTP server, so the check must not depend on it.)
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]

CMD ["python", "-m", "bot.main"]
