# Document Processing Agentic Flow — Azure / container image
# Build API:  docker build --build-arg APP_TARGET=api -t doc-agent-api .
# Build UI:   docker build --build-arg APP_TARGET=ui  -t doc-agent-ui .

FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    GRADIO_HOST=0.0.0.0 \
    GRADIO_PORT=7860 \
    STORAGE_BASE_PATH=/home/data/storage \
    SQLITE_DATABASE_PATH=/home/data/app.db

# System deps for lxml / python-docx friendly base
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

# Dependency layer (better cache)
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY samples ./samples

RUN uv sync --frozen --no-dev \
    && mkdir -p /home/data/storage/jobs /home/data/storage/audio

ARG APP_TARGET=api
ENV APP_TARGET=${APP_TARGET}

EXPOSE 8000 7860

# Azure App Service sets WEBSITES_PORT; we bind via API_PORT / GRADIO_PORT env.
CMD ["sh", "-c", "if [ \"$APP_TARGET\" = \"ui\" ]; then uv run doc-ui; else uv run doc-api; fi"]
