FROM node:22-bookworm-slim AS javascript

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOWNLOAD_DIR=/app/downloads
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
ARG UPGRADE_EXTRACTORS=0
RUN if [ "$UPGRADE_EXTRACTORS" = "1" ]; then pip install --upgrade 'yt-dlp[default]' gallery-dl; fi
COPY backend ./backend
COPY frontend ./frontend
COPY scripts ./scripts
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/downloads \
    && chown app:app /app/downloads
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
ENTRYPOINT ["tini", "-g", "--"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
