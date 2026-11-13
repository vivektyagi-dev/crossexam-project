"""End to end through the real API, real Celery task code (eager mode), real PostgreSQL,
real Redis, real LangChain agents and middleware - with the scripted fake model.

Checks every layer the proposal promises: dedupe, classification and splitting of
bundles, extraction, grouping into shipment packs, the match engine against planted
problems, supervisor routing, the exception agent pausing for human approval, role
limits, resume after approval, idempotent export, and the cost ledger.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client(eager_celery):
    from app.api.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def uploaded(client, generated_data):
    files = sorted((generated_data / "files").iterdir())
    payload = [("files", (f.name, f.read_bytes())) for f in files]
    r = client.post("/batches", files=payload, data={"name": "e2e", "priority": "normal"},
                    headers={"X-User": "priya", "X-Role": "ap_executive"})
    assert r.status_code == 200, r.text
    return r.json(), len(files)


def test_every_file_processed(client, uploaded):
    body, n = uploaded
    assert body["accepted"] == n
    status = client.get(f"/batches/{body['batch_id']}").json()
    assert status["status"] == "grouped"
    assert "failed" not in status["documents"], status["documents"]


def test_reupload_is_deduplicated(client, uploaded, generated_data):
    f = sorted((generated_data / "files").iterdir())[0]
    r = client.post("/batches", files=[("files", (f.name, f.read_bytes()))], headers={"X-User": "priya"})
    assert r.json()["accepted"] == 0 and len(r.json()["duplicate_files"]) == 1


def test_planted_problems_are_caught(client, uploaded, generated_data):
    truth = json.loads((generated_data / "ground_truth.json").read_text())
    packs = {p["po_number"]: p for p in client.get("/packs", params={"batch_id": uploaded[0]["batch_id"]}).json()}
    misses, false_alarms = [], []
    for s in truth["shipments"]:
        pack = packs.get(s["po_number"])
        assert pack is not None, f"no pack for {s['po_number']}"
        found = set(pack["issue_codes"]) - {"LOW_CONFIDENCE"}
        expected = set(s["expected_issue_codes"])
        if not expected <= found:
            misses.append((s["po_number"], expected - found))
        if not expected and pack["status"] not in ("auto_approved",):
            false_alarms.append((s["po_number"], pack["status"], found))
    assert not misses, misses
    assert not false_alarms, false_alarms


def test_injection_goes_to_a_person(client, uploaded, generated_data):
    truth = json.loads((generated_data / "ground_truth.json").read_text())
    po = next(s["po_number"] for s in truth["shipments"] if "injection" in s["problems"])
    pack = next(p for p in client.get("/packs").json() if p["po_number"] == po)
    assert pack["status"] == "needs_review"
    assert "SUSPICIOUS_CONTENT" in pack["issue_codes"]


def test_human_approval_flow_and_export(client, uploaded):
    waiting = client.get("/packs", params={"status": "awaiting_approval"}).json()
    assert waiting, "expected at least one pack waiting for approval"
    small = None
    for p in waiting:
        detail = client.get(f"/packs/{p['id']}").json()
        pending = [a for a in detail["actions"] if a["status"] == "pending"]
        assert any(a["tool"] == "propose_fix" for a in pending)
        if all(a["requires_role"] == "ap_executive" for a in pending):
            small = (p, pending)
        else:
            # an executive may not approve above the limit
            r = client.post(f"/packs/{p['id']}/decisions", headers={"X-User": "priya", "X-Role": "ap_executive"},
                            json={"decisions": [{"action_id": a["id"], "type": "approve"} for a in pending]})
            assert r.status_code == 403
            r = client.post(f"/packs/{p['id']}/decisions", headers={"X-User": "arjun", "X-Role": "finance_manager"},
                            json={"decisions": [{"action_id": a["id"], "type": "approve"} for a in pending]})
            assert r.status_code == 200, r.text
            after = client.get(f"/packs/{p['id']}").json()
            assert after["status"] in ("approved", "needs_review"), after["status"]
    if small:
        p, pending = small
        r = client.post(f"/packs/{p['id']}/decisions", headers={"X-User": "priya", "X-Role": "ap_executive"},
                        json={"decisions": [{"action_id": a["id"], "type": "approve"} for a in pending]})
        assert r.status_code == 200

    exp1 = client.post("/exports", headers={"X-User": "priya"})
    rows1 = int(exp1.headers["X-Export-Rows"])
    assert rows1 > 0
    exp2 = client.post("/exports", headers={"X-User": "priya"})
    assert int(exp2.headers["X-Export-Rows"]) == 0  # each invoice exported exactly once

    outbox = client.get("/outbox").json()
    assert outbox, "approved supplier emails should be queued"


def test_cost_ledger_and_stats(client, uploaded):
    stats = client.get("/stats").json()
    assert stats["documents_extracted"] > 0
    assert "extractor_invoice" in stats["cost_by_agent_usd"]
    assert stats["automation_rate"] > 0


def test_demo_master_data_never_replaces_existing(db):
    from app.db.seed import seed_demo

    assert seed_demo(60) is None  # this session's master data is already loaded


def test_dashboard_activity_matches_stats(client, uploaded):
    """The Grafana activity panels read the same database as the Monitoring page."""
    from decimal import Decimal

    from app.api import main

    stats = client.get("/stats?hours=1").json()
    assert {route: n for route, n in main.packs_routed_last_hour().items() if n} == stats["routes"]
    spend = main.ai_spend_last_hour_by_agent()
    assert {agent: str(Decimal(v).quantize(Decimal("0.0001"))) for agent, v in spend.items()} == stats["cost_by_agent_usd"]
    assert set(main.documents_per_minute()) == {"extracted", "failed"}
    assert set(main.tokens_per_minute()) == {"input", "output"}
    assert all(seconds >= 0 for seconds in main.llm_latency_p95().values())
