FROM python:3.12-slim

# Install system dependencies needed by ChromaDB and BeautifulSoup
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (better layer caching)
COPY examples/webhook/sports-rag/python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared base modules
COPY examples/shared/base_event_detector.py examples/shared/base_event_store.py examples/shared/base_state_tracker.py ./

# Copy application source
COPY examples/webhook/sports-rag/python/ingest.py examples/webhook/sports-rag/python/server.py ./
COPY examples/webhook/sports-rag/python/event_detector.py examples/webhook/sports-rag/python/event_store.py examples/webhook/sports-rag/python/match_state.py ./

# ChromaDB persistence directory (mounted as a volume in production)
RUN mkdir -p /data/chroma
ENV CHROMA_PERSIST_DIR=/data/chroma

# Expose the port Cloud Run will listen on
EXPOSE 8080

# Use the PORT environment variable injected by Cloud Run (default 8080)
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
