#!/bin/sh
# Container entrypoint: the first argument picks the component.
set -e

# On GKE, Secret Manager secrets are mounted as files named after the variable they fill
# (infra/k8s/base/secrets.yaml). Terraform gives keys a deployment does not use the value
# "unused", because a mount fails on a secret with no version; those stay unset.
SECRETS_DIR="${SECRETS_DIR:-/var/run/secrets/crossexam}"
for f in "$SECRETS_DIR"/*; do
  [ -f "$f" ] || continue
  value=$(cat "$f")
  [ "$value" = "unused" ] || export "$(basename "$f")=$value"
done

PORT="${PORT:-8000}"
CONCURRENCY="${CELERY_CONCURRENCY:-8}"

case "$1" in
  api)
    exec uvicorn app.api.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers ;;
  web)
    # Serves the built React screen and forwards /api to the API (adds an identity token when API_AUTH=gcp).
    exec uvicorn app.ui.server:app --host 0.0.0.0 --port "$PORT" --proxy-headers ;;
  reader)
    # Thread pool: the work is mostly waiting on the vision model and storage.
    exec celery -A app.workers.celery_app worker -n "reader@%h" \
         -Q reader.urgent,reader.normal,reader.bulk --pool threads -c "$CONCURRENCY" -l INFO ;;
  agent)
    exec celery -A app.workers.celery_app worker -n "agent@%h" \
         -Q agent.urgent,agent.normal,agent.bulk --pool threads -c "$CONCURRENCY" -l INFO ;;
  beat)
    # Exactly ONE beat process may run, or every scheduled job runs twice.
    exec celery -A app.workers.celery_app beat -l INFO --schedule /tmp/celerybeat-schedule ;;
  flower)
    exec celery -A app.workers.celery_app flower --port="${PORT:-5555}" ;;
  migrate)
    python -m app.db.session
    # The GKE migrate job sets DEMO_SHIPMENTS: an empty database then gets the demo master data.
    [ "${DEMO_SHIPMENTS:-0}" = 0 ] || exec python -m app.db.seed --demo "$DEMO_SHIPMENTS" ;;
  seed)
    shift; exec python -m app.db.seed "$@" ;;
  *)
    exec "$@" ;;
esac
