# Build from this folder: docker build -t ip-api .
FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV API_HOST=0.0.0.0 API_PORT=8000
ENV STORAGE_BASE_PATH=/home/data/storage SQLITE_DATABASE_PATH=/home/data/app.db
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
COPY . .
RUN uv pip install --system -e . \
    && mkdir -p /home/data/storage/jobs /home/data/storage/audio
ENV MAF_BASE_URL=http://central-agentic-flow:8003
EXPOSE 8000
CMD ["python", "run.py"]
