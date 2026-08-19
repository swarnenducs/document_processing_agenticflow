# Build from this folder: docker build -t ui-app .
FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV GRADIO_HOST=0.0.0.0 GRADIO_PORT=7860
ENV API_BASE_URL=http://ip-api:8000
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
COPY . .
RUN uv pip install --system -e .
EXPOSE 7860
CMD ["python", "run.py"]
