FROM python:3.12-slim

# Install system dependencies (needed by chromadb and lxml/bs4)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY server.py ingest.py worker.py ./

# ChromaDB persistence directory (mount a volume or use CHROMA_PERSIST_DIR)
RUN mkdir -p /data/chroma

# Environment defaults - override via Cloud Run env vars or docker run -e
ENV CHROMA_PERSIST_DIR=/data/chroma \
    VECTOR_STORE_BACKEND=chroma \
    VECTOR_STORE_DURABLE=false \
    LLM_MODEL=ollama/llama3.2 \
    EMBEDDING_MODEL=text-embedding-3-small \
    REFRESH_INTERVAL_MINUTES=60 \
    TOP_K=4 \
    PORT=8080

EXPOSE 8080

# Healthcheck for Cloud Run / Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
