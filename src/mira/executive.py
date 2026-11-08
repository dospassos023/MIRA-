"""Durable orchestration for explicitly registered, trusted tools."""
import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Literal, Mapping, Protocol
from uuid import uuid4

from pydantic import Field, JsonValue, ValidationError, field_validator

from .cognitive import CognitiveEngine, EvidenceRecord, Step
from .memory import Conflict, Memory, now, timestamp
from .policy import SAFE
from .schemas import Action, Context, Key, Operation, Schema, Short


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ToolSpec(Schema):
    name: Key
    version: Short
    scope: Short
    capability: Action
    boundary: Literal["read_only", "sandbox", "consequential"]
    confidential_transfer: bool = False
    timeout: float = Field(default=5, gt=0, le=60)
    retries: int = Field(default=0, ge=0, le=2)

    @property
    def permission(self) -> Literal["allowed", "approval_required"]:
        if self.confidential_transfer or self.boundary == "consequential":
            return "approval_required"
        if self.capability in SAFE or (
            self.boundary == "sandbox" and self.capability == Action.MODIFY_RECORD
        ):
            return "allowed"
        return "approval_required"


class Effect(Schema):
    code: Key
    changed: bool = True
    rollback: dict[str, JsonValue] | None = None


class Observation(Schema):
    code: Key
    summary: Short
    sources: list[Short] = Field(min_length=1, max_length=20)


class NoEffect(RuntimeError):
    """A trusted adapter proved there were no effects and a retry could help."""


class ApprovalExpired(RuntimeError):
    pass


class Tool(Protocol):
    spec: ToolSpec
    input_schema: type[Schema]

    async def execute(self, args: Schema, operation_id: str) -> Effect: ...
    async def verify(self, args: Schema, effect: Effect) -> Observation: ...
    async def rollback(self, args: Schema, effect: Effect) -> Observation: ...


class Call(Schema):
    tool: Key
    args: dict[str, JsonValue]
    after_code: Key | None = None

    @field_validator("args")
    @classmethod
    def finite_json(cls, value):
        canonical(value)
        return value


class TaskRequest(Schema):
    request_key: Short
    goal: Short
    calls: list[Call] = Field(min_length=1, max_length=12)
    context: Context = Field(default_factory=Context)
    evidence_ids: list[Short] = Field(default_factory=list, max_length=20)


class ApprovalRequest(Schema):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    ttl_seconds: int = Field(default=300, ge=1, le=3600)


@dataclass(frozen=True)
class PlannedCall:
    tool: Tool
    args: Schema
    condition: str | None
    spec: ToolSpec

    def snapshot(self):
        return {
            "tool": self.spec.model_dump(mode="json"),
            "args": self.args.model_dump(mode="json"),
            "after_code": self.condition,
        }


class Executive:
    def __init__(self, memory: Memory, tools: Mapping[str, Tool] | None = None):
        self.memory = memory
        self.cognitive = CognitiveEngine(memory)
        self.tools = MappingProxyType(dict(tools or {}))
        self.specs = {key: ToolSpec.model_validate(tool.spec.model_dump())
                      for key, tool in self.tools.items()}
        if any(key != spec.name for key, spec in self.specs.items()):
            raise ValueError("Registry names must match tool declarations")

    def capabilities(self):
        return [{**spec.model_dump(mode="json"), "permission": spec.permission,
                 "input_schema": self.tools[key].input_schema.model_json_schema()}
                for key, spec in sorted(self.specs.items())]

    def _resolve(self, calls):
        result = []
        for index, call in enumerate(calls):
            if call.tool not in self.tools:
                raise ValueError(f"Tool is not registered: {call.tool}")
            if index == 0 and call.after_code is not None:
                raise ValueError("First call cannot depend on a previous outcome")
            tool = self.tools[call.tool]
            result.append(PlannedCall(tool, tool.input_schema.model_validate(call.args),
                                      call.after_code, self.specs[call.tool]))
        return result

    @staticmethod
    def _event(db, task_id, kind, detail, step=None):
        db.execute(
            """INSERT INTO executive_events(task_id, kind, step, detail, recorded_at)
               VALUES (?,?,?,?,?)""", (task_id, kind, step, canonical(detail), now()),
        )

    @staticmethod
    def _task(db, task_id):
        row = db.execute("SELECT * FROM executive_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return row

    def get(self, task_id):
        with self.memory.connect() as db:
            row = dict(self._task(db, task_id))
            row.pop("request")
            row["plan"] = json.loads(row["plan"])
            for key in ("requires_approval", "escalation"):
                row[key] = bool(row[key])
            row["events"] = [
                {**dict(event), "detail": json.loads(event["detail"])}
                for event in db.execute(
                    "SELECT * FROM executive_events WHERE task_id=? ORDER BY sequence", (task_id,)
                )
            ]
        return row

    def submit(self, request: TaskRequest):
        body = canonical(request.model_dump(mode="json"))
        with self.memory.connect(write=True) as db:
            existing = db.execute(
                "SELECT id, request FROM executive_tasks WHERE request_key=?",
                (request.request_key,),
            ).fetchone()
            if existing:
                if body != existing["request"]:
                    raise Conflict("Request key already refers to a different task")
                task_id = existing["id"]
            else:
                task_id = str(uuid4())
                self._queue(db, task_id, request, body)
        return self.get(task_id)

    def _queue(self, db, task_id, request, body):
        requires_approval = False
        try:
            calls = self._resolve(request.calls)
            records = [self.cognitive.evidence(key) for key in request.evidence_ids]
            assessment = self.cognitive.assess(records)
            steps = [
                Step(description=call.spec.name, operation=Operation(
                    id=f"{task_id}:{index}", action=call.spec.capability, target=call.spec.scope,
                ))
                for index, call in enumerate(calls)
            ]
            context = request.context
            if assessment["contradiction"]:
                context = context.model_copy(update={"risk": max(context.risk or 0, 0.7)})
            cognitive_plan = self.cognitive.plan(request.goal, steps, context)
            plan = {
                "goal": request.goal,
                "assessment": assessment,
                "evidence": [record.model_dump(mode="json") for record in records],
                "cognitive_steps": [step.model_dump(mode="json") for step in cognitive_plan],
                "calls": [call.snapshot() for call in calls],
            }
            requires_approval = any(call.spec.permission == "approval_required" for call in calls)
            state = "awaiting_approval" if requires_approval else "queued"
            summary = "Exact plan requires owner approval." if requires_approval else "Queued for execution."
        except ValidationError:
            plan, state, summary = {"goal": request.goal}, "failed", "Tool arguments were denied."
        except (ValueError, KeyError) as error:
            plan, state, summary = {"goal": request.goal}, "failed", (
                str(error) if isinstance(error, ValueError) else "Required evidence is missing."
            )
        serialized = canonical(plan)
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        db.execute(
            """INSERT INTO executive_tasks
               (id,request_key,request,plan,digest,state,requires_approval,created_at,summary)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (task_id, request.request_key, body, serialized, digest, state,
             requires_approval, now(), summary),
        )
        self._event(db, task_id, "denied" if state == "failed" else state, {"summary": summary})

    def approve(self, task_id, approval: ApprovalRequest):
        with self.memory.connect(write=True) as db:
            task = self._task(db, task_id)
            if task["digest"] != approval.digest or task["state"] != "awaiting_approval":
                raise Conflict("Approval must match a task awaiting approval and its exact digest")
            expires = timestamp(datetime.now(UTC) + timedelta(seconds=approval.ttl_seconds))
            db.execute(
                "UPDATE executive_tasks SET state='queued', approved_until=?, summary=? WHERE id=?",
                (expires, "Approved and queued.", task_id),
            )
            self._event(db, task_id, "approved", {"digest": approval.digest, "expires": expires})
        return self.get(task_id)

    def _claim(self, task_id):
        with self.memory.connect(write=True) as db:
            task = self._task(db, task_id)
            if task["state"] != "queued" or db.execute(
                "SELECT 1 FROM executive_tasks WHERE state='running' LIMIT 1"
            ).fetchone():
                return None
            expires = task["approved_until"]
            if task["requires_approval"] and (expires is None or expires <= now()):
                db.execute(
                    """UPDATE executive_tasks SET state='awaiting_approval',
                       approved_until=NULL, summary='Approval expired.' WHERE id=?""", (task_id,),
                )
                self._event(db, task_id, "approval_expired", {})
                return None
            plan = json.loads(task["plan"])
            try:
                calls = self._resolve(TaskRequest.model_validate_json(task["request"]).calls)
            except (ValidationError, ValueError):
                calls = []
            if not calls or [call.snapshot() for call in calls] != plan["calls"]:
                self._finish(db, task_id, "failed", "Tool contract changed after planning.", True)
                return None
            # One owner claims the task. A failed or interrupted claim is never replayed.
            seconds = sum(call.spec.timeout * (call.spec.retries + 3) for call in calls) + 30
            db.execute(
                """UPDATE executive_tasks SET state='running', started_at=?, deadline_at=?,
                   approved_until=NULL, summary='Running.' WHERE id=?""",
                (now(), timestamp(datetime.now(UTC) + timedelta(seconds=seconds)), task_id),
            )
            self._event(db, task_id, "claimed", {"approval_consumed": bool(expires)})
            return calls, expires

    def _finish(self, db, task_id, state, summary, escalation=False):
        db.execute(
            "UPDATE executive_tasks SET state=?, summary=?, escalation=? WHERE id=?",
            (state, summary, escalation, task_id),
        )
        self._event(db, task_id, state, {"summary": summary, "escalation": escalation})

    def recover(self, task_id):
        """Operator confirms the worker has stopped. Never dispatch uncertain work again."""
        with self.memory.connect(write=True) as db:
            task = self._task(db, task_id)
            if task["state"] != "running" or task["deadline_at"] > now():
                raise Conflict("Only overdue running tasks can be recovered")
            self._finish(db, task_id, "failed",
                         "Worker outcome unknown. Reconcile recorded operations before retrying.", True)
        return self.get(task_id)

    def _record(self, task_id, kind, detail, index):
        with self.memory.connect(write=True) as db:
            if self._task(db, task_id)["state"] != "running":
                raise Conflict("Task is no longer owned by this worker")
            self._event(db, task_id, kind, detail, index)

    async def run(self, task_id):
        claim = self._claim(task_id)
        if claim is None:
            return self.get(task_id)
        calls, expires = claim
        effects = []
        last_code = None
        failure = None
        uncertain = False
        for index, call in enumerate(calls):
            if call.condition is not None and call.condition != last_code:
                failure = "Observed result did not authorize the planned branch."
                break
            if call.spec.permission == "approval_required" and (expires is None or expires <= now()):
                failure = "Approval expired before dispatch."
                break
            operation_id = f"{task_id}:{index}"
            try:
                effect = await self._execute(task_id, index, call, operation_id, expires)
            except ApprovalExpired:
                failure = "Approval expired before dispatch."
                break
            except NoEffect:
                failure = "Tool reported no effect after allowed attempts."
                break
            except Exception:
                failure, uncertain = "Execution outcome is unknown. Reconciliation required.", True
                break
            effects.append((index, call, effect))
            self._record(task_id, "executed", {"code": effect.code, "changed": effect.changed,
                         "rollback_available": effect.rollback is not None}, index)
            try:
                observation = await asyncio.wait_for(call.tool.verify(call.args, effect), call.spec.timeout)
                self._observe(task_id, index, operation_id, "verified", observation)
                last_code = observation.code
            except Exception:
                failure = "The tool outcome could not be verified."
                break

        rolled_back = False
        if failure:
            self._record(task_id, "step_failed", {"summary": failure, "uncertain": uncertain}, index)
        if failure and not uncertain:
            rolled_back, uncertain = await self._rollback(task_id, effects)
        with self.memory.connect(write=True) as db:
            if self._task(db, task_id)["state"] == "running":
                state = "rolled_back" if rolled_back and not uncertain else ("failed" if failure else "completed")
                self._finish(db, task_id, state, failure or "Every dispatched step was verified.", uncertain)
        return self.get(task_id)

    async def _execute(self, task_id, index, call, operation_id, expires):
        for attempt in range(call.spec.retries + 1):
            if call.spec.permission == "approval_required" and (expires is None or expires <= now()):
                raise ApprovalExpired
            self._record(task_id, "dispatch", {"operation_id": operation_id, "attempt": attempt + 1}, index)
            try:
                effect = await asyncio.wait_for(call.tool.execute(call.args, operation_id), call.spec.timeout)
                if not isinstance(effect, Effect):
                    raise TypeError("Invalid tool effect")
                return effect
            except NoEffect:
                self._record(task_id, "no_effect", {"attempt": attempt + 1}, index)
                if attempt == call.spec.retries:
                    raise
        raise AssertionError("Unreachable retry state")

    def _observe(self, task_id, index, operation_id, kind, observation):
        if not isinstance(observation, Observation):
            raise TypeError("Tool verification did not return structured evidence")
        record = EvidenceRecord(id=f"{operation_id}:{kind}", claim=observation.summary,
                                status="supported", confidence=1, sources=observation.sources)
        self.cognitive.record_evidence(record)
        self._record(task_id, kind, {**observation.model_dump(), "evidence_id": record.id}, index)

    async def _rollback(self, task_id, effects):
        restored, uncertain = False, False
        for index, call, effect in reversed(effects):
            if effect.rollback is None and (call.spec.boundary == "read_only" or not effect.changed):
                continue
            if effect.rollback is None or call.spec.permission == "approval_required":
                # A compensating consequential action requires its own authorization.
                uncertain = True
                self._record(task_id, "rollback_unavailable", {}, index)
                continue
            self._record(task_id, "rollback_dispatch", {}, index)
            try:
                result = await asyncio.wait_for(call.tool.rollback(call.args, effect), call.spec.timeout)
                self._observe(task_id, index, f"{task_id}:{index}", "rollback_verified", result)
                restored = True
            except Exception:
                uncertain = True
                self._record(task_id, "rollback_failed", {}, index)
        return restored, uncertain
