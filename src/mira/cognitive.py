"""Deterministic cognitive workflow primitives; generation never grants authority."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import Field

from .memory import Memory, now
from .policy import SAFE, authorized
from .schemas import Approval, Context, Operation, Schema, Short, Unit, Value


class EvidenceRecord(Schema):
    id: Short
    claim: Value
    status: Literal["supported", "disputed", "unknown", "retracted"] = "unknown"
    confidence: Unit = 0
    sources: list[Short] = Field(default_factory=list, max_length=50)


class Step(Schema):
    description: Short
    operation: Operation | None = None
    reversible: bool = True


class ToolOutcome(Schema):
    success: bool
    observed: bool = False
    summary: Short
    evidence: list[Short] = Field(default_factory=list)
    rollback_token: str | None = None


class TaskResult(Schema):
    run_id: str
    state: Literal["verified", "failed", "escalated", "rolled_back"]
    completed_steps: int
    summary: str


class Executor(Protocol):
    async def execute(self, operation: Operation) -> ToolOutcome: ...
    async def rollback(self, token: str) -> ToolOutcome: ...


class CognitiveEngine:
    """Evidence ledger, planning, hard permission gate, observed outcomes and feedback."""
    def __init__(self, memory: Memory):
        self.memory = memory

    def record_evidence(self, record: EvidenceRecord):
        with self.memory.connect(write=True) as db:
            db.execute("INSERT INTO evidence_ledger VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET claim=excluded.claim,status=excluded.status,confidence=excluded.confidence,sources=excluded.sources",
                       (record.id, record.claim, record.status, record.confidence, json.dumps(record.sources), now()))

    def evidence(self, record_id: str) -> EvidenceRecord:
        with self.memory.connect() as db:
            row = db.execute("SELECT * FROM evidence_ledger WHERE id=?", (record_id,)).fetchone()
        if row is None: raise KeyError(record_id)
        return EvidenceRecord(id=row["id"], claim=row["claim"], status=row["status"], confidence=row["confidence"], sources=json.loads(row["sources"]))

    @staticmethod
    def assess(records: list[EvidenceRecord]) -> dict:
        active = [r for r in records if r.status != "retracted"]
        statuses = {r.status for r in active}
        conflict = "disputed" in statuses or ("supported" in statuses and "unknown" in statuses)
        return {"uncertain": not active or any(r.status == "unknown" for r in active),
                "contradiction": conflict,
                "confidence": min((r.confidence for r in active if r.status == "supported"), default=0.0)}

    @staticmethod
    def plan(goal: str, steps: list[Step], context: Context) -> list[Step]:
        # Risk changes effort/timing; permission checks remain hard gates at execution.
        if context.risk is not None and context.risk >= .7 or context.reversible is False:
            return [Step(description="Assess evidence, risks, and reversibility before acting"), *steps]
        return steps

    async def run(self, goal: str, steps: list[Step], executor: Executor, context: Context,
                  *, approval: Approval | None = None) -> TaskResult:
        run_id = str(uuid.uuid4()); plan = self.plan(goal, steps, context)
        with self.memory.connect(write=True) as db:
            db.execute("INSERT INTO cognitive_runs VALUES (?,?,?,?,?,?)", (run_id, goal, json.dumps([s.model_dump(mode="json") for s in plan]), "running", None, now()))
        completed = 0; tokens: list[str] = []
        for step in plan:
            op = step.operation
            if op is None: continue
            if op.action not in SAFE and not authorized(op, trusted_approval=approval):
                state, message = "escalated", "Approval required before this operation."
                break
            outcome = await executor.execute(op)
            if outcome.rollback_token:
                tokens.append(outcome.rollback_token)
            if not outcome.success or not outcome.observed:
                # A model/executor assertion without an observed result is never reported as success.
                state, message = "failed", "Outcome could not be independently observed."
                if tokens:
                    rollback = await executor.rollback(tokens[-1])
                    if rollback.success and rollback.observed: state = "rolled_back"
                break
            completed += 1
        else:
            state, message = "verified", "All requested operations were observed successfully."
        with self.memory.connect(write=True) as db:
            db.execute("UPDATE cognitive_runs SET state=? WHERE id=?", (state, run_id))
        return TaskResult(run_id=run_id, state=state, completed_steps=completed, summary=message)

    def feedback(self, run_id: str, feedback: str):
        with self.memory.connect(write=True) as db:
            if not db.execute("UPDATE cognitive_runs SET feedback=? WHERE id=?", (feedback, run_id)).rowcount:
                raise KeyError(run_id)

