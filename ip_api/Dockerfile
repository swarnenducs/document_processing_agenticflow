FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV API_HOST=0.0.0.0 API_PORT=8000
ENV STORAGE_BASE_PATH=/home/data/storage SQLITE_DATABASE_PATH=/home/data/app.db
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
# Monorepo: ip_api still imports document graph for job streaming; include both packages.
COPY document-processing-mcp ./document-processing-mcp
COPY voice_enable_mcp ./voice_enable_mcp
COPY ip_api ./ip_api
COPY samples ./samples
RUN uv pip install --system \
      -e ./document-processing-mcp \
      -e ./voice_enable_mcp \
      -e ./ip_api \
    && mkdir -p /home/data/storage/jobs /home/data/storage/audio
ENV DOCUMENT_MCP_URL=http://document-processing-mcp:8001/mcp
ENV VOICE_MCP_URL=http://voice-enable-mcp:8002/mcp
ENV MAF_BASE_URL=http://central-agentic-flow:8003
ENV DOCUMENT_PROMPTS_DIR=/app/document-processing-mcp/prompts
EXPOSE 8000
CMD ["doc-api"]
