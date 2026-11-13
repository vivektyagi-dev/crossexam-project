"""OpenTelemetry tracing. One trace follows a document from upload, through the queue
(Celery instrumentation propagates the context), into every worker and database call.
Agent-level detail (prompts, tool calls) lives in LangSmith, tagged with the same ids."""

from __future__ import annotations

from app.config import settings

_done = False


def setup_tracing(fastapi_app=None, celery: bool = False) -> None:
    global _done
    if settings.otel_exporter == "none":
        return
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    if not _done:
        provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
        if settings.otel_exporter == "gcp":
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter(project_id=settings.gcp_project or None)
        elif settings.otel_exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter()
        else:
            exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from app.db.session import engine

        SQLAlchemyInstrumentor().instrument(engine=engine)
        _done = True
    if fastapi_app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(fastapi_app, excluded_urls="healthz,readyz,metrics")
    if celery:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()


def current_trace_id() -> str | None:
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        return format(ctx.trace_id, "032x") if ctx and ctx.is_valid else None
    except Exception:
        return None
