"""Metrics through the OpenTelemetry API.

Locally they are exposed for Prometheus on METRICS_PORT; on GCP they go straight to
Cloud Monitoring (workload.googleapis.com/...), which works from Cloud Run worker pools
where there is nothing to scrape.

Instruments are created at import time from the global (proxy) meter; they start
recording for real once setup_metrics() installs a provider in the process.
"""

from __future__ import annotations

from opentelemetry import metrics as otel_metrics

from app.config import settings

_started = False


def setup_metrics(start_http_server: bool = True) -> None:
    """Call once per process (API startup, Celery worker_process_init)."""
    global _started
    if _started or settings.metrics_exporter == "none":
        return
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": settings.service_name})
    readers = []
    if settings.metrics_exporter == "prometheus":
        from opentelemetry.exporter.prometheus import PrometheusMetricReader

        readers.append(PrometheusMetricReader())
        if start_http_server:
            from prometheus_client import start_http_server as start

            try:
                start(settings.metrics_port)
            except OSError:
                pass  # another process in this container already serves metrics
    elif settings.metrics_exporter == "gcp":
        from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        readers.append(PeriodicExportingMetricReader(
            CloudMonitoringMetricsExporter(project_id=settings.gcp_project or None, add_unique_identifier=True),
            export_interval_millis=60_000))
    otel_metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))
    _started = True


_m = otel_metrics.get_meter("crossexam")

docs_processed = _m.create_counter("crossexam_documents_processed", description="Documents by type and outcome")
task_duration = _m.create_histogram("crossexam_task_duration_seconds", unit="s")
task_failures = _m.create_counter("crossexam_task_failures")
packs_routed = _m.create_counter("crossexam_packs_routed", description="Packs by route")
llm_tokens = _m.create_counter("crossexam_llm_tokens")
llm_cost = _m.create_counter("crossexam_llm_cost_usd", description="AI spend in US dollars")
llm_latency = _m.create_histogram("crossexam_llm_latency_seconds", unit="s")
llm_calls = _m.create_counter("crossexam_llm_calls")
ratelimit_wait = _m.create_histogram("crossexam_ratelimit_wait_seconds", unit="s")
injection_blocked = _m.create_counter("crossexam_injection_blocked")
cache_hits = _m.create_counter("crossexam_llm_cache_hits")


def register_queue_gauge(read_lengths) -> None:
    """Observable gauge for queue length per queue (the API process reads Redis)."""
    from opentelemetry.metrics import Observation

    def callback(_options):
        try:
            return [Observation(n, {"queue": q}) for q, n in read_lengths().items()]
        except Exception:
            return []

    _m.create_observable_gauge("crossexam_queue_length", callbacks=[callback])


def register_status_gauges(documents, packs, spend, injections) -> None:
    """Observable gauges the API process reads from PostgreSQL on every scrape: documents and
    packs per status, the AI spend in the cost ledger and the documents the injection guard
    cleaned. The counters above live in worker memory, so they restart at zero with each
    worker, and increase() cannot see the first increment of a new series; these always match
    the database, and so the web screen."""
    from opentelemetry.metrics import Observation

    def by_status(read_counts):
        def callback(_options):
            try:
                return [Observation(n, {"status": s}) for s, n in read_counts().items()]
            except Exception:
                return []

        return callback

    def total(read):
        def callback(_options):
            try:
                return [Observation(float(read()))]
            except Exception:
                return []

        return callback

    _m.create_observable_gauge("crossexam_documents", callbacks=[by_status(documents)],
                               description="Documents per status, from the database")
    _m.create_observable_gauge("crossexam_packs", callbacks=[by_status(packs)],
                               description="Shipment packs per status, from the database")
    _m.create_observable_gauge("crossexam_ai_spend_usd", callbacks=[total(spend)],
                               description="AI spend in the cost ledger, from the database")
    _m.create_observable_gauge("crossexam_injection_documents", callbacks=[total(injections)],
                               description="Documents the injection guard cleaned, from the database")


def register_activity_gauges(documents_per_minute, packs_routed, spend_by_agent, tokens_per_minute,
                             latency_p95) -> None:
    """Observable gauges for the dashboard's activity panels, read from PostgreSQL over a recent
    window on every scrape. rate() and increase() on the worker counters miss the first
    increment of each new series, and at demo volume most series only ever get one: a routed
    pack showed as none. Each reader returns {label value: number} for its window."""
    from opentelemetry.metrics import Observation

    def by_label(label, read, quiet_as_zero=True):
        seen: set[str] = set()

        def callback(_options):
            try:
                values = read()
            except Exception:
                return []
            if not quiet_as_zero:
                return [Observation(float(v), {label: k}) for k, v in values.items()]
            seen.update(values)  # an agent that goes quiet drops to 0 instead of vanishing
            return [Observation(float(values.get(k, 0)), {label: k}) for k in sorted(seen)]

        return callback

    _m.create_observable_gauge("crossexam_documents_per_minute", callbacks=[by_label("outcome", documents_per_minute)],
                               description="Documents extracted or failed per minute over the last 5 minutes, from the database")
    _m.create_observable_gauge("crossexam_packs_routed_last_hour", callbacks=[by_label("route", packs_routed)],
                               description="Packs created in the last hour by route, from the database")
    _m.create_observable_gauge("crossexam_ai_spend_last_hour_usd", callbacks=[by_label("agent", spend_by_agent)],
                               description="AI spend in the last hour by agent, from the cost ledger")
    _m.create_observable_gauge("crossexam_llm_tokens_per_minute", callbacks=[by_label("direction", tokens_per_minute)],
                               description="Tokens per minute over the last 5 minutes, from the cost ledger")
    # A model with no calls has no latency, so its line ends rather than dropping to 0.
    _m.create_observable_gauge("crossexam_llm_latency_p95_seconds",
                               callbacks=[by_label("model", latency_p95, quiet_as_zero=False)],
                               description="p95 model-call latency over the last 5 minutes, from the cost ledger")
