"""Business-level health numbers for the dashboard and the nightly check."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.db.models import DocStatus, Document, EvalRun, Extraction, LLMCall, ShipmentPack
from app.db.session import session_scope


def quality_snapshot(hours: int = 24, record: bool = False) -> dict:
    since = datetime.now(UTC) - timedelta(hours=hours)
    with session_scope() as s:
        docs = s.scalar(select(func.count()).select_from(Document).where(
            Document.created_at >= since, Document.status == DocStatus.extracted)) or 0
        failed = s.scalar(select(func.count()).select_from(Document).where(
            Document.created_at >= since, Document.status == DocStatus.failed)) or 0
        low_conf = s.scalar(select(func.count()).select_from(Extraction).where(
            Extraction.created_at >= since, Extraction.confidence < 0.8)) or 0
        escalated = s.scalar(select(func.count()).select_from(Extraction).where(
            Extraction.created_at >= since, Extraction.escalated.is_(True))) or 0
        packs = dict(s.execute(select(ShipmentPack.status, func.count()).where(ShipmentPack.created_at >= since)
                               .group_by(ShipmentPack.status)).all())
        cost = s.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(LLMCall.created_at >= since))
        cost_by_agent = dict(s.execute(select(LLMCall.agent, func.sum(LLMCall.cost_usd)).where(
            LLMCall.created_at >= since).group_by(LLMCall.agent)).all())
        routes = dict(s.execute(select(ShipmentPack.route, func.count()).where(
            ShipmentPack.created_at >= since, ShipmentPack.route.isnot(None), ShipmentPack.route != "wait")
            .group_by(ShipmentPack.route)).all())
        decided = sum(routes.values())
        auto = routes.get("auto_approve", 0)
        out = {
            "window_hours": hours,
            "documents_extracted": docs,
            "documents_failed": failed,
            "low_confidence_rate": round(low_conf / docs, 4) if docs else 0,
            "escalation_rate": round(escalated / docs, 4) if docs else 0,
            "packs": {k.value: v for k, v in packs.items()},
            "routes": routes,
            "automation_rate": round(auto / decided, 4) if decided else 0,
            "llm_cost_usd": str(Decimal(cost or 0).quantize(Decimal("0.0001"))),
            "cost_per_document_usd": str((Decimal(cost or 0) / docs).quantize(Decimal("0.000001"))) if docs else "0",
            "cost_by_agent_usd": {k: str(Decimal(v).quantize(Decimal("0.0001"))) for k, v in cost_by_agent.items()},
        }
        if record:
            s.add(EvalRun(name="nightly_quality_check", metrics=out))
        return out
