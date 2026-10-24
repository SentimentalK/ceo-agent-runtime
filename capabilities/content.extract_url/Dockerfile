# Production image for Content Resolver service
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Install system dependencies (curl for healthcheck, ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 10001 -m -s /bin/sh appuser

WORKDIR /app

# Install lightweight resolver dependencies
COPY requirements-resolver.txt .
RUN pip install --no-cache-dir -r requirements-resolver.txt

# Copy source code and capability declaration
COPY capabilities.yaml .
COPY src/ ./src/

RUN chown -R appuser:appuser /app
USER 10001:10001

# Health check using the unauthenticated /healthz endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1

EXPOSE 8000

# Run lightweight FastAPI resolver service
CMD ["uvicorn", "src.service:app", "--host", "0.0.0.0", "--port", "8000"]
