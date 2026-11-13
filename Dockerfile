# One image for every component; the command decides what it runs:
#   api     uvicorn app.api.main:app
#   web     uvicorn app.ui.server:app (the React screen built below, plus the /api proxy)
#   reader  celery worker on reader.* queues
#   agent   celery worker on agent.* queues
#   migrate python -m app.db.session

# The web screen (React + TypeScript) is built here and copied in as static files.
FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY datagen ./datagen
COPY eval ./eval
COPY --from=web /web/dist ./web/dist
COPY scripts/docker-entrypoint.sh /usr/local/bin/entrypoint
RUN sed -i "s/\r$//" /usr/local/bin/entrypoint && chmod +x /usr/local/bin/entrypoint \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/storage && chown -R appuser /app/data

USER appuser
EXPOSE 8000 8080 9100
ENTRYPOINT ["entrypoint"]
CMD ["api"]
