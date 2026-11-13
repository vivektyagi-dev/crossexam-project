"""A scripted chat model for tests and CI: it plays each agent's part using the data
generator's ground truth, so the whole pipeline (queues, middleware, tools, human
approval, export) can be exercised end to end without an API key or any cost.

It is NOT a stand-in for measuring AI accuracy - use a real provider for that.

Enable with:  LLM_PROVIDER=fake  FAKE_LLM_FACTORY=tests.fake_llm:factory
              FAKE_GROUND_TRUTH=data/generated/ground_truth.json
"""

from __future__ import annotations

import itertools
import json
import os
import re
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_ids = itertools.count(1)


@lru_cache
def ground_truth() -> dict:
    path = os.environ.get("FAKE_GROUND_TRUTH", "data/generated/ground_truth.json")
    data = json.loads(open(path).read())
    return {f["file"]: f for f in data["files"]}


def _call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}"}],
                     usage_metadata={"input_tokens": 800, "output_tokens": 120, "total_tokens": 920})


def _calls(*pairs: tuple[str, dict]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"call_{next(_ids)}"} for n, a in pairs],
                     usage_metadata={"input_tokens": 900, "output_tokens": 200, "total_tokens": 1100})


def _text(msg: BaseMessage) -> str:
    c = msg.content
    return c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict))


class ScriptedChatModel(BaseChatModel):
    model: str = "fake-model"
    bound: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools, **kwargs):
        names = []
        for t in tools:
            names.append(t["name"] if isinstance(t, dict) and "name" in t else
                         t.get("function", {}).get("name") if isinstance(t, dict) else getattr(t, "name", str(t)))
        return self.model_copy(update={"bound": names})

    def _structured_name(self, *candidates: str) -> str:
        for c in candidates:
            if c in self.bound:
                return c
        return candidates[0]

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        msg = self._respond(messages)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    # ------------------------------------------------------------------ roles
    def _respond(self, messages: list[BaseMessage]) -> AIMessage:
        system = next((_text(m) for m in messages if isinstance(m, SystemMessage)), "")
        tools_done = [m for m in messages if isinstance(m, ToolMessage)]
        human = "\n".join(_text(m) for m in messages if m.type == "human")
        if "transcribe scanned" in system:
            return AIMessage(content="[scanned page transcription]",
                             usage_metadata={"input_tokens": 1500, "output_tokens": 400, "total_tokens": 1900})
        if "document classifier" in system:
            return self._classify(human)
        if "extraction specialist" in system:
            return self._extract(human)
        if "reconciliation specialist" in system:
            return self._reconcile(tools_done)
        if "supervisor for one shipment pack" in system:
            return self._supervise(tools_done)
        if "exception specialist" in system:
            return self._exception(tools_done)
        return AIMessage(content="Summary of earlier steps.",
                         usage_metadata={"input_tokens": 100, "output_tokens": 30, "total_tokens": 130})

    def _classify(self, human: str) -> AIMessage:
        fname = re.search(r"File: (.+)", human).group(1).strip()
        entry = ground_truth().get(fname)
        n_pages = int(re.search(r"Pages: (\d+)", human).group(1))
        if entry is None:
            segs = [{"doc_type": "other", "start_page": 1, "end_page": n_pages, "reason": "unknown"}]
        else:
            segs = [{"doc_type": s["doc_type"], "start_page": s["pages"][0], "end_page": s["pages"][1],
                     "reason": "title"} for s in entry["segments"]]
        return _call(self._structured_name("Classification"), {"segments": segs, "confidence": 0.96})

    def _extract(self, human: str) -> AIMessage:
        fname = re.search(r"File: (.+)", human).group(1).strip()
        page = 1
        m = re.match(r"(.+) \[p(\d+)-(\d+)\]$", fname)
        if m:
            fname, page = m.group(1), int(m.group(2))
        doc_type = re.search(r"Document type: (\w+)", human).group(1)
        entry = ground_truth()[fname]
        seg = next(s for s in entry["segments"] if s["pages"][0] == page or len(entry["segments"]) == 1)
        fields = dict(seg["fields"])
        fields.pop("supplier", None)
        fields.update({"confidence": 0.95, "uncertain_fields": []})
        schema = {"invoice": "InvoiceData", "packing_list": "PackingListData", "lorry_receipt": "LorryReceiptData",
                  "eway_bill": "EwayBillData", "quality_certificate": "QualityCertificateData"}.get(doc_type,
                                                                                               "AdjustmentNoteData")
        return _call(self._structured_name(schema), json.loads(json.dumps(fields, default=str)))

    def _reconcile(self, done: list[ToolMessage]) -> AIMessage:
        if not done:
            return _call("match_engine", {})
        result = json.loads(done[-1].content) if done[-1].content.startswith("{") else {"ok": False}
        return _call(self._structured_name("ReconciliationReport"), {
            "decision": "clean" if result.get("ok") else "exception",
            "summary": "Papers compared by the match engine. " + "; ".join(i["message"] for i in result.get("issues", []))[:400],
            "linked_document_ids": []})

    def _supervise(self, done: list[ToolMessage]) -> AIMessage:
        if not done:
            return _call("run_reconciler", {})
        report = json.loads(done[-1].content)
        route = "auto_approve" if report.get("decision") == "clean" else "investigate"
        return _call(self._structured_name("SupervisorDecision"),
                     {"route": route, "summary": report.get("summary", ""), "confidence": 0.9})

    def _exception(self, done: list[ToolMessage]) -> AIMessage:
        names = [m.name for m in done]
        if "match_engine" not in names:
            return _call("match_engine", {})
        if "propose_fix" not in names:
            result = json.loads(next(m for m in done if m.name == "match_engine").content)
            codes = {i["code"] for i in result["issues"]}
            finding = " ".join(i["message"] for i in result["issues"] if i["severity"] == "block")
            calls = [("propose_fix", {
                "action": "hold" if codes & {"POSSIBLE_DUPLICATE", "MISSING_COA", "COA_FAILED", "SHORT_SHELF_LIFE"}
                else "pay_adjusted",
                "pay_amount": float(result["payable_amount"]), "debit_note_amount": float(result["debit_note_amount"]),
                "finding": finding or "Papers disagree.",
                "explanation": "Pay only for what was received at the agreed price; request a debit note."})]
            if float(result["debit_note_amount"]) > 0:
                calls.append(("draft_supplier_email", {
                    "to_address": "accounts@supplier-example.in", "subject": "Debit note request",
                    "body": f"Please issue a debit note for Rs {result['debit_note_amount']}. {finding}"}))
            return _calls(*calls)
        return _call(self._structured_name("ExceptionFinding"), {
            "finding": "Investigated and resolved after review.", "root_cause": "see match engine",
            "recommended_action": "as approved", "similar_case_ids": [], "confidence": 0.9})


def factory(model_name: str) -> ScriptedChatModel:
    return ScriptedChatModel(model=f"fake-{model_name}")
