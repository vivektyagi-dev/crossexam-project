"""Celery: bulk orchestration.

Two worker pools consume different queues so each scales for the right reason:
  reader.*  - format detection, PDF rendering, vision transcription (one task per page)
  agent.*   - classifier, extractors, supervisor, reconciler, exception resolver

Each pool listens to urgent, normal and bulk queues in that order. With the Redis broker a
worker pops from the first non-empty queue in its list, so urgent work is never stuck
behind a month-end backlog.
"""

from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init, worker_ready

from app.config import settings

PRIORITIES = ("urgent", "normal", "bulk")
READER_QUEUES = [f"reader.{p}" for p in PRIORITIES]
AGENT_QUEUES = [f"agent.{p}" for p in PRIORITIES]

celery_app = Celery("crossexam", broker=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_ignore_result=True,  # results live in PostgreSQL, not in the broker
    task_acks_late=True,  # a task is removed from the queue only after it finishes...
    task_reject_on_worker_lost=True,  # ...so a killed worker's task is redelivered
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 3600},
    broker_connection_retry_on_startup=True,
    task_default_queue="agent.normal",
    task_soft_time_limit=600,
    task_time_limit=660,
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        "reap-stale-work": {"task": "app.workers.tasks.reap_stale", "schedule": 300.0,
                            "options": {"queue": "agent.urgent"}},
        "nightly-quality-check": {"task": "app.workers.tasks.nightly_quality_check", "schedule": 86400.0,
                                  "options": {"queue": "agent.bulk"}},
    },
)


@worker_process_init.connect
def _init_process(**_):
    from app.observability.logging import configure_logging
    from app.observability.metrics import setup_metrics
    from app.observability.tracing import setup_tracing

    configure_logging()
    setup_metrics(start_http_server=True)
    setup_tracing(celery=True)


@worker_ready.connect
def _ready(**_):
    # thread/solo pools don't fire worker_process_init
    _init_process()


def queue_for(kind: str, priority: str) -> str:
    p = priority if priority in PRIORITIES else "normal"
    return f"{kind}.{p}"
