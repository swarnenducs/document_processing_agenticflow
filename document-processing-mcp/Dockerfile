# Build from repo root — self-contained (no shared_core package)
FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
COPY document-processing-mcp ./document-processing-mcp
RUN uv pip install --system -e ./document-processing-mcp
ENV DOCUMENT_MCP_HOST=0.0.0.0 DOCUMENT_MCP_PORT=8001
ENV DOCUMENT_PROMPTS_DIR=/app/document-processing-mcp/prompts
EXPOSE 8001
CMD ["document-process-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8001"]
