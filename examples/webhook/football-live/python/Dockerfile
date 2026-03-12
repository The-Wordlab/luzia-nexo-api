FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/chroma

ENV CHROMA_PERSIST_DIR=/data/chroma \
    VECTOR_STORE_BACKEND=pgvector \
    VECTOR_STORE_DURABLE=false

EXPOSE 8003

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8003"]
