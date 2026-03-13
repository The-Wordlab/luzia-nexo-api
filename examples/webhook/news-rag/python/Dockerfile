FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY server.py ingest.py ./

# Environment defaults — override via Cloud Run env vars or docker run -e
ENV VECTOR_STORE_BACKEND=pgvector \
    VECTOR_STORE_DURABLE=false \
    LLM_MODEL=vertex_ai/gemini-2.5-flash \
    EMBEDDING_MODEL=vertex_ai/text-embedding-004 \
    REFRESH_INTERVAL_MINUTES=30 \
    TOP_K=5 \
    PORT=8080

EXPOSE 8080

# Healthcheck for Cloud Run / Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
