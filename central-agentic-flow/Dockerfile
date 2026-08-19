# Build from this folder: docker build -t central-agentic-flow .
FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
COPY . .
RUN uv pip install --system -e .
ENV MAF_HOST=0.0.0.0 MAF_PORT=8003
ENV MAF_PROMPTS_DIR=/app/prompts
ENV MAF_MCP_REGISTRY_FILE=/app/config/mcp_registry.yml
ENV DOCUMENT_MCP_URL=http://document-processing-mcp:8001/mcp
ENV VOICE_MCP_URL=http://voice-enable-mcp:8002/mcp
EXPOSE 8003
CMD ["python", "run.py"]
