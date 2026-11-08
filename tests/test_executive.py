import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from asgi_client import TestClient
from mira.api import create_app
from mira.config import Settings
from mira.executive import ApprovalRequest, Effect, Executive, NoEffect, Observation, TaskRequest, ToolSpec
from mira.memory import Conflict, Memory, timestamp
from mira.sandbox import BROKEN, NoArguments, benchmark, fixture, registry

OWNER = {"Authorization": "Bearer " + "a" * 32}
LINDA = {"Authorization": "Bearer " + "b" * 32}


class Adapter:
    input_schema = NoArguments

    def __init__(self, name="test", **changes):
        self.spec = ToolSpec(**{
            "name": name, "version": "1", "scope": "synthetic:test",
            "capability": "analyze", "boundary": "read_only",
            **changes,
        })
        self.operations = []
        self.fail_once = False
        self.slow = False
        self.unverified = False
        self.on_execute = None
        self.on_rollback = None

    async def execute(self, args, operation_id):
        self.operations.append(operation_id)
        if self.on_execute:
            self.on_execute()
        if self.fail_once and len(self.operations) == 1:
            raise NoEffect
        if self.slow:
            await asyncio.sleep(60)
        return Effect(code="effect", rollback={} if self.spec.boundary == "sandbox" else None)

    async def verify(self, args, effect):
        if self.unverified:
            raise ValueError("No confirmation")
        return Observation(code="verified", summary="Observed fixture effect", sources=["synthetic:record"])

    async def rollback(self, args, effect):
        self.on_rollback()
        return Observation(code="restored", summary="Observed fixture restore", sources=["synthetic:restore"])


def request(key, *tools):
    return TaskRequest(
        request_key=key, goal="Synthetic executive task",
        calls=[{"tool": tool, "args": {}} for tool in tools],
    )


@pytest.fixture
def memory(tmp_path):
    return Memory(tmp_path / "vault.sqlite3")


def test_sandbox_end_to_end():
    report = asyncio.run(benchmark())
    assert report["executive_state"] == "completed"
    assert report["shortcut_denied"] and report["duplicate_dispatch_prevented"]
    assert report["independent_index_check"]
    assert [item["code"] for item in report["observations"]] == ["index.stale", "index.valid", "index.valid"]


@pytest.mark.parametrize("contract", [
    {"capability": "purchase", "boundary": "sandbox"},
    {"capability": "send", "boundary": "read_only"},
    {"confidential_transfer": True},
    {"capability": "modify_record", "boundary": "consequential"},
])
def test_consequential_http_actions_wait_for_exact_owner_approval(tmp_path, contract):
    adapter = Adapter(**contract)
    settings = Settings("a" * 32, tmp_path / "vault", linda_token="b" * 32)
    with TestClient(create_app(settings, tools={"test": adapter})) as client:
        body = request("consequential", "test").model_dump(mode="json")
        assert client.post("/v1/tasks", headers=LINDA, json=body).status_code == 403
        task = client.post("/v1/tasks", headers=OWNER, json=body).json()
        path = f"/v1/tasks/{task['id']}"
        assert task["state"] == "awaiting_approval"
        assert client.post(path + "/run", headers=OWNER).json()["state"] == "awaiting_approval"
        assert not adapter.operations
        assert client.post(path + "/approval", headers=LINDA, json={"digest": task["digest"]}).status_code == 403
        assert client.post(path + "/approval", headers=OWNER, json={"digest": "0" * 64}).status_code == 409
        assert client.post(path + "/approval", headers=OWNER, json={"digest": task["digest"]}).json()["state"] == "queued"
        assert client.post(path + "/approval", headers=OWNER, json={"digest": task["digest"]}).status_code == 409
        result = client.post(path + "/run", headers=OWNER).json()
        assert result["state"] == "completed"
        assert any(event["kind"] == "verified" for event in result["events"])
        assert client.post(path + "/run", headers=OWNER).json() == result
        assert client.post("/v1/tasks", headers=OWNER, json=body).json() == result
        assert len(adapter.operations) == 1
        assert client.post("/v1/tasks", headers=OWNER, json={**body, "goal": "Changed"}).status_code == 409


def test_api_real_pipeline_and_reopened_state(tmp_path):
    pipeline = fixture(tmp_path / "pipeline")
    settings = Settings("a" * 32, tmp_path / "vault")
    with TestClient(create_app(settings, tools=registry(pipeline))) as client:
        body = request("research", "diagnose_index", "repair_index", "verify_index").model_dump(mode="json")
        body["calls"][1]["after_code"] = "index.stale"
        task = client.post("/v1/tasks", headers=OWNER, json=body).json()
        assert task["state"] == "queued"
        result = client.post(f"/v1/tasks/{task['id']}/run", headers=OWNER).json()
        assert result["state"] == "completed"
        assert pipeline.index.read_bytes() == b'{"ids":["A","B"]}\n'
    with TestClient(create_app(settings, tools=registry(pipeline))) as client:
        assert client.get(f"/v1/tasks/{task['id']}", headers=OWNER).json() == result


def test_safe_retry_uses_same_operation_id(memory):
    tool = Adapter(retries=1)
    tool.fail_once = True
    runtime = Executive(memory, {"test": tool})
    result = asyncio.run(runtime.run(runtime.submit(request("retry", "test"))["id"]))
    assert result["state"] == "completed"
    assert len(tool.operations) == 2 and len(set(tool.operations)) == 1
    assert [item["kind"] for item in result["events"]].count("no_effect") == 1


def test_expired_approval_requires_new_approval_and_never_retries_expired(memory, monkeypatch):
    import mira.executive as module

    tool = Adapter(capability="send", retries=1)
    tool.fail_once = True
    runtime = Executive(memory, {"test": tool})
    task = runtime.submit(request("expires", "test"))
    approval = ApprovalRequest(digest=task["digest"])
    runtime.approve(task["id"], approval)
    real_now = module.now
    future = timestamp(datetime.now(UTC) + timedelta(days=1))
    monkeypatch.setattr(module, "now", lambda: future)
    assert asyncio.run(runtime.run(task["id"]))["state"] == "awaiting_approval"
    assert not tool.operations
    monkeypatch.setattr(module, "now", real_now)
    runtime.approve(task["id"], approval)
    tool.on_execute = lambda: monkeypatch.setattr(module, "now", lambda: future)
    result = asyncio.run(runtime.run(task["id"]))
    assert result["state"] == "failed"
    assert result["summary"] == "Approval expired before dispatch."
    assert len(tool.operations) == 1


def test_unverified_result_rolls_back_real_file_and_records_evidence(memory, tmp_path):
    pipeline = fixture(tmp_path / "pipeline")
    verifier = Adapter()
    verifier.unverified = True
    runtime = Executive(memory, {**registry(pipeline), "test": verifier})
    task = runtime.submit(request("undo", "repair_index", "test"))
    result = asyncio.run(runtime.run(task["id"]))
    assert result["state"] == "rolled_back"
    assert pipeline.index.read_bytes() == BROKEN
    event = next(item for item in result["events"] if item["kind"] == "rollback_verified")
    assert runtime.cognitive.evidence(event["detail"]["evidence_id"]).status == "supported"


def test_rollback_reverses_order_and_escalates_failed_restore(memory):
    first = Adapter("first", boundary="sandbox")
    second = Adapter("second", boundary="sandbox")
    second.unverified = True
    order = []
    first.on_rollback = lambda: order.append("first")

    def fail_restore():
        order.append("second")
        raise RuntimeError("Unable to restore")

    second.on_rollback = fail_restore
    runtime = Executive(memory, {"first": first, "second": second})
    result = asyncio.run(runtime.run(runtime.submit(request("undo-fail", "first", "second"))["id"]))
    assert result["state"] == "failed" and result["escalation"]
    assert order == ["second", "first"]
    assert any(item["kind"] == "rollback_failed" for item in result["events"])


def test_timeout_outcome_unknown_never_retried(memory):
    adapter = Adapter(timeout=0.01, retries=2)
    adapter.slow = True
    runtime = Executive(memory, {"test": adapter})
    task_id = runtime.submit(request("timeout", "test"))["id"]
    result = asyncio.run(runtime.run(task_id))
    assert result["state"] == "failed" and result["escalation"]
    assert asyncio.run(runtime.run(task_id)) == result
    assert len(adapter.operations) == 1


def test_concurrent_claim_and_interrupted_worker_are_never_replayed(memory):
    adapter = Adapter(timeout=30)
    adapter.slow = True
    runtime = Executive(memory, {"test": adapter})
    task_id = runtime.submit(request("interrupted", "test"))["id"]

    async def interrupt():
        worker = asyncio.create_task(runtime.run(task_id))
        while not adapter.operations:
            await asyncio.sleep(0)
        other = Executive(Memory(memory.path), {"test": adapter})
        assert (await other.run(task_id))["state"] == "running"
        with pytest.raises(Conflict):
            other.recover(task_id)
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker

    asyncio.run(interrupt())
    with memory.connect(write=True) as db:
        db.execute("UPDATE executive_tasks SET deadline_at=? WHERE id=?",
                   (timestamp(datetime.now(UTC) - timedelta(seconds=1)), task_id))
    other = Executive(Memory(memory.path), {"test": adapter})
    result = other.recover(task_id)
    assert result["state"] == "failed" and result["escalation"]
    assert asyncio.run(other.run(task_id)) == result
    assert len(adapter.operations) == 1


@pytest.mark.parametrize("change", [{"version": "2"}, {"scope": "synthetic:other"}])
def test_contract_change_after_approval_prevents_execution(memory, change):
    original = Adapter(capability="purchase")
    runtime = Executive(memory, {"test": original})
    task = runtime.submit(request("change", "test"))
    runtime.approve(task["id"], ApprovalRequest(digest=task["digest"]))
    replacement = Adapter(capability="purchase", **change)
    other = Executive(Memory(memory.path), {"test": replacement})
    result = asyncio.run(other.run(task["id"]))
    assert result["state"] == "failed" and result["escalation"]
    assert not replacement.operations


def test_upgrade_keeps_cognitive_evidence_and_installs_runtime_schema(tmp_path):
    import sqlite3
    from importlib.resources import files

    path = tmp_path / "pre-executive.sqlite3"
    path.touch(mode=0o600)
    db = sqlite3.connect(path)
    try:
        db.execute("CREATE TABLE schema_migrations (name TEXT PRIMARY KEY)")
        migrations = files("mira").joinpath("migrations")
        for name in ("001_initial.sql", "002_indexes.sql", "003_cognitive.sql"):
            db.executescript(migrations.joinpath(name).read_text(encoding="utf-8"))
            db.execute("INSERT INTO schema_migrations VALUES (?)", (name,))
        db.execute("INSERT INTO evidence_ledger VALUES (?,?,?,?,?,?)",
                   ("existing", "Prior observation", "supported", 1, '["source"]', "before"))
        db.commit()
    finally:
        db.close()
    runtime = Executive(Memory(path), {"test": Adapter()})
    assert runtime.cognitive.evidence("existing").claim == "Prior observation"
    assert runtime.submit(request("after-upgrade", "test"))["state"] == "queued"
