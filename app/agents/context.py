"""Runtime context passed to every agent run (LangChain `context_schema`).

Middleware and tools read the ids from here to label cost rows and traces, and write
flags (e.g. possible prompt injection) that the pipeline acts on after the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentContext:
    agent: str
    batch_id: str | None = None
    document_id: str | None = None
    pack_id: str | None = None
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def flag(self, name: str, note: str = "") -> None:
        if name not in self.flags:
            self.flags.append(name)
        if note:
            self.notes.append(note)

    def run_config(self, extra_tags: list[str] | None = None) -> dict:
        """LangChain run config: names and metadata show up in LangSmith traces."""
        meta = {k: v for k, v in {"batch_id": self.batch_id, "document_id": self.document_id,
                                  "pack_id": self.pack_id, "agent": self.agent}.items() if v}
        return {"run_name": self.agent, "tags": [self.agent, *(extra_tags or [])], "metadata": meta}
