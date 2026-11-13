"""Write tools. Only the exception agent has them, and HumanInTheLoopMiddleware holds
every call until a person approves, edits or rejects it. Each write carries an
idempotency key, so a retry after approval can never send or record anything twice.

ERP export is deliberately NOT a tool: no agent can move an invoice towards payment.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from langchain.tools import ToolRuntime, tool
from sqlalchemy import select

from app.agents.context import AgentContext
from app.agents.llm import embed_text
from app.db.models import EmailOutbox, PackStatus, Resolution, ShipmentPack
from app.db.session import session_scope


@tool
def draft_supplier_email(to_address: str, subject: str, body: str, runtime: ToolRuntime[AgentContext]) -> str:
    """Queue an email to the supplier (e.g. asking for a debit note or a corrected invoice).
    A person must approve it before it is queued. Be factual and polite; cite document numbers."""
    pack_id = runtime.context.pack_id
    # hashed so the key fits the 80-character column whatever the subject's length
    key = f"email:{pack_id}:{hashlib.sha256(subject.strip().lower().encode()).hexdigest()[:16]}"
    with session_scope() as s:
        if s.scalars(select(EmailOutbox).where(EmailOutbox.idempotency_key == key)).first():
            return "This email was already queued; nothing new was sent."
        s.add(EmailOutbox(idempotency_key=key, pack_id=pack_id, to_address=to_address, subject=subject,
                          body=body, approved_by="see pending_actions"))
    return f"Email to {to_address} queued for sending."


@tool
def propose_fix(action: str, pay_amount: float, debit_note_amount: float, finding: str, explanation: str,
                runtime: ToolRuntime[AgentContext]) -> str:
    """Record the resolution for this pack. Use the payable and debit-note amounts from
    match_engine - do not compute your own. A person must approve before it is recorded.

    action: 'pay_adjusted' | 'pay_in_full' | 'hold' | 'reject'
    finding: what is wrong, in plain words, citing documents
    explanation: why this action, and what happens next
    """
    pack_id = runtime.context.pack_id
    with session_scope() as s:
        pack = s.get(ShipmentPack, pack_id)
        existing = s.scalars(select(Resolution).where(Resolution.pack_id == pack_id)).first()
        if existing:
            return "A resolution is already recorded for this pack."
        summary = finding
        pack.finding = finding
        s.add(Resolution(pack_id=pack_id, supplier_gstin=pack.supplier_gstin or "", issue_codes=pack.issue_codes,
                         summary=summary, resolution=f"{action}: {explanation}",
                         pay_amount=Decimal(str(pay_amount)), debit_note_amount=Decimal(str(debit_note_amount)),
                         embedding=embed_text(f"{summary}\n{explanation}")))
        pack.proposal = {"action": action, "pay_amount": pay_amount, "debit_note_amount": debit_note_amount,
                         "finding": finding, "explanation": explanation}
        pack.payable_amount = Decimal(str(pay_amount))
        pack.status = PackStatus.rejected if action == "reject" else (
            PackStatus.needs_review if action == "hold" else PackStatus.approved)
    return f"Resolution recorded: {action}, pay {pay_amount}, debit note {debit_note_amount}."


WRITE_TOOLS = [draft_supplier_email, propose_fix]

HITL_CONFIG = {
    "draft_supplier_email": {"allowed_decisions": ["approve", "edit", "reject"],
                             "description": "Send this email to the supplier?"},
    "propose_fix": {"allowed_decisions": ["approve", "edit", "reject"],
                    "description": "Record this resolution and release the adjusted amount for payment?"},
}
