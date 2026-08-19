# Build from this folder: docker build -t voice-enable-mcp .
FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
COPY . .
RUN uv pip install --system -e .
ENV VOICE_MCP_HOST=0.0.0.0 VOICE_MCP_PORT=8002
ENV VOICE_PROMPTS_DIR=/app/prompts
EXPOSE 8002
CMD ["python", "run.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8002"]
