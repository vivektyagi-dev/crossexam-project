"""Celery tasks: thin wrappers that add queues, retries, logging ids and metrics around
the pipeline steps in app/services/pipeline.py."""

from __future__ import annotations

import time
from contextlib import contextmanager

import redis
from celery.exceptions import SoftTimeLimitExceeded

from app.config import settings
from app.observability import metrics
from app.observability.logging import bind, clear, get_logger
from app.services import pipeline
from app.workers.celery_app import celery_app, queue_for

log = get_logger(__name__)
_redis = redis.Redis.from_url(settings.redis_url)

# Transient failures worth retrying with backoff (rate limits, timeouts, network).
RETRYABLE = (TimeoutError, ConnectionError, OSError)


@contextmanager
def _observe(task: str, **ids):
    clear()
    bind(task=task, **ids)
    started = time.perf_counter()
    try:
        yield
        metrics.task_duration.record(time.perf_counter() - started, {"task": task, "ok": "true"})
    except Exception as exc:
        metrics.task_duration.record(time.perf_counter() - started, {"task": task, "ok": "false"})
        metrics.task_failures.add(1, {"task": task, "error": type(exc).__name__})
        log.exception("task_failed", error=str(exc))
        raise
    finally:
        clear()


def _progress(batch_id: str | None, field: str) -> None:
    if batch_id:
        try:
            _redis.hincrby(f"progress:{batch_id}", field, 1)
            _redis.expire(f"progress:{batch_id}", 7 * 86400)
        except redis.RedisError:
            pass  # progress counters are a convenience; the database is the truth


def enqueue_document(doc_id: str, priority: str = "normal") -> None:
    read_document.apply_async((doc_id,), queue=queue_for("reader", priority))


# ------------------------------------------------------------------------------- reading
@celery_app.task(bind=True, max_retries=5, autoretry_for=RETRYABLE, retry_backoff=True, retry_jitter=True)
def read_document(self, doc_id: str) -> None:
    with _observe("read_document", document_id=doc_id):
        prio = pipeline.priority_of_doc(doc_id).value
        try:
            out = pipeline.read_step(doc_id)
        except (SoftTimeLimitExceeded, *RETRYABLE):
            raise
        except Exception as exc:  # unreadable file: record it, don't retry forever
            pipeline.fail_document(doc_id, f"read failed: {exc}")
            _after_terminal(doc_id)
            return
        if out["next"] == "vision":
            _redis.delete(f"pages_done:{doc_id}", f"classify_enqueued:{doc_id}")
            _redis.set(f"pages_total:{doc_id}", len(out["pages"]), ex=86400)
            for i in out["pages"]:
                transcribe_page.apply_async((doc_id, i), queue=queue_for("reader", prio))
        elif out["next"] == "classify":
            _progress(_batch_of(doc_id), "read")
            classify_document.apply_async((doc_id,), queue=queue_for("agent", prio))
        elif out["next"] == "done":
            _progress(_batch_of(doc_id), "extracted")
            _after_terminal(doc_id)


@celery_app.task(bind=True, max_retries=5, autoretry_for=RETRYABLE, retry_backoff=True, retry_jitter=True)
def transcribe_page(self, doc_id: str, page_index: int) -> None:
    """One page per task: a 40-page bundle is read by many workers in parallel. The last
    page to finish (tracked in a Redis set, safe under redelivery) triggers classification."""
    with _observe("transcribe_page", document_id=doc_id, page=page_index):
        pipeline.transcribe_step(doc_id, page_index)
        _redis.sadd(f"pages_done:{doc_id}", page_index)
        _redis.expire(f"pages_done:{doc_id}", 86400)
        total = int(_redis.get(f"pages_total:{doc_id}") or 0)
        if _redis.scard(f"pages_done:{doc_id}") >= total and _redis.set(f"classify_enqueued:{doc_id}", 1,
                                                                         nx=True, ex=86400):
            pipeline.mark_read(doc_id)
            _progress(_batch_of(doc_id), "read")
            classify_document.apply_async((doc_id,), queue=queue_for("agent", pipeline.priority_of_doc(doc_id).value))


# ------------------------------------------------------------------------------- agents
@celery_app.task(bind=True, max_retries=4, autoretry_for=RETRYABLE, retry_backoff=True, retry_jitter=True)
def classify_document(self, doc_id: str) -> None:
    with _observe("classify_document", document_id=doc_id):
        prio = pipeline.priority_of_doc(doc_id).value
        try:
            ready = pipeline.classify_step(doc_id)
        except (SoftTimeLimitExceeded, *RETRYABLE):
            raise
        except Exception as exc:
            if self.request.retries < 2:
                raise self.retry(exc=exc, countdown=30) from exc
            pipeline.fail_document(doc_id, f"classification failed: {exc}")
            _after_terminal(doc_id)
            return
        for child in ready:
            extract_document.apply_async((child,), queue=queue_for("agent", prio))
        if not ready:
            _after_terminal(doc_id)


@celery_app.task(bind=True, max_retries=4, autoretry_for=RETRYABLE, retry_backoff=True, retry_jitter=True)
def extract_document(self, doc_id: str) -> None:
    with _observe("extract_document", document_id=doc_id):
        try:
            pipeline.extract_step(doc_id)
            _progress(_batch_of(doc_id), "extracted")
        except (SoftTimeLimitExceeded, *RETRYABLE):
            raise
        except Exception as exc:
            if self.request.retries < 2:
                raise self.retry(exc=exc, countdown=30) from exc
            pipeline.fail_document(doc_id, f"extraction failed: {exc}")
            _progress(_batch_of(doc_id), "failed")
        _after_terminal(doc_id)


def _batch_of(doc_id: str) -> str | None:
    from app.db.models import Document
    from app.db.session import session_scope

    with session_scope() as s:
        doc = s.get(Document, doc_id)
        return doc.batch_id if doc else None


def _after_terminal(doc_id: str) -> None:
    batch_id = _batch_of(doc_id)
    if batch_id and pipeline.try_finish_batch(batch_id):
        group_batch.apply_async((batch_id,), queue="agent.urgent")


@celery_app.task(bind=True, max_retries=3, autoretry_for=RETRYABLE, retry_backoff=True)
def group_batch(self, batch_id: str) -> None:
    with _observe("group_batch", batch_id=batch_id):
        for pack_id in pipeline.group_step(batch_id):
            process_pack.apply_async((pack_id,), queue=queue_for("agent", pipeline.priority_of_pack(pack_id).value))


@celery_app.task(bind=True, max_retries=4, autoretry_for=RETRYABLE, retry_backoff=True, retry_jitter=True)
def process_pack(self, pack_id: str) -> None:
    with _observe("process_pack", pack_id=pack_id):
        route = pipeline.process_pack_step(pack_id)
        if route == "investigate":
            investigate_pack.apply_async((pack_id,), queue=queue_for("agent", pipeline.priority_of_pack(pack_id).value))


@celery_app.task(bind=True, max_retries=4, autoretry_for=RETRYABLE, retry_backoff=True, retry_jitter=True)
def investigate_pack(self, pack_id: str) -> None:
    with _observe("investigate_pack", pack_id=pack_id):
        pipeline.investigate_step(pack_id)


@celery_app.task(bind=True, max_retries=4, autoretry_for=RETRYABLE, retry_backoff=True, retry_jitter=True)
def resume_pack(self, pack_id: str, resume: dict) -> None:
    with _observe("resume_pack", pack_id=pack_id):
        pipeline.resume_step(pack_id, resume)


# ------------------------------------------------------------------------------- housekeeping
@celery_app.task
def reap_stale() -> dict:
    with _observe("reap_stale"):
        found = pipeline.reap_stale()
        for doc_id in found["read"]:
            read_document.apply_async((doc_id,), queue="reader.urgent")
        for doc_id in found["classify"]:
            classify_document.apply_async((doc_id,), queue="agent.urgent")
        for doc_id in found["extract"]:
            extract_document.apply_async((doc_id,), queue="agent.urgent")
        for pack_id in found["process"]:
            process_pack.apply_async((pack_id,), queue="agent.urgent")
        for pack_id in found["investigate"]:
            investigate_pack.apply_async((pack_id,), queue="agent.urgent")
        for batch_id in found["finish"]:
            if pipeline.try_finish_batch(batch_id):
                group_batch.apply_async((batch_id,), queue="agent.urgent")
        counts = {k: len(v) for k, v in found.items()}
        if any(counts.values()):
            log.warning("requeued_stale_work", **counts)
        return counts


@celery_app.task
def nightly_quality_check() -> dict:
    with _observe("nightly_quality_check"):
        from app.services.quality import quality_snapshot

        return quality_snapshot(record=True)
