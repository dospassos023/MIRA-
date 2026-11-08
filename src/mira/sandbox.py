"""A disposable, synthetic research index pipeline with no network or shell access."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import perf_counter

from .cognitive import EvidenceRecord
from .executive import Effect, Executive, Observation, TaskRequest, ToolSpec, canonical
from .memory import Memory
from .schemas import Schema

SOURCE = [{"id": "A", "finding": "yield increased"}, {"id": "B", "finding": "no change"}]
BROKEN = b'{"ids":["A"]}\n'
EXPECTED_INDEX = b'{"ids":["A","B"]}\n'


class NoArguments(Schema):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Pipeline:
    def __init__(self, root: Path):
        self.scope = f"synthetic-pipeline:{digest(os.fsencode(root.resolve()))}"
        self.source = root / "findings.json"
        self.index = root / "index.json"

    def expected(self):
        findings = json.loads(self.source.read_bytes())
        return (canonical({"ids": sorted(row["id"] for row in findings)}) + "\n").encode()

    def replace(self, expected_before: bytes, replacement: bytes):
        if self.index.read_bytes() != expected_before:
            raise RuntimeError("Index changed since inspection")
        with NamedTemporaryFile(dir=self.index.parent, delete=False) as temporary:
            path = Path(temporary.name)
            try:
                temporary.write(replacement)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary.close()
                path.replace(self.index)
            finally:
                path.unlink(missing_ok=True)

    def inspect(self):
        current, expected = self.index.read_bytes(), self.expected()
        matches = current == expected
        return Observation(
            code="index.valid" if matches else "index.stale",
            summary="Index matches the source findings." if matches else "Index omits source findings.",
            sources=[f"index.json:sha256:{digest(current)}",
                     f"expected-index:sha256:{digest(expected)}"],
        )


class InspectIndex:
    input_schema = NoArguments

    def __init__(self, pipeline: Pipeline, name: str):
        self.pipeline = pipeline
        self.spec = ToolSpec(name=name, version="1", scope=pipeline.scope,
                             capability="analyze", boundary="read_only")

    async def execute(self, args, operation_id):
        return Effect(code="inspection")

    async def verify(self, args, effect):
        result = self.pipeline.inspect()
        if self.spec.name == "verify_index" and result.code != "index.valid":
            raise RuntimeError("Research index verification failed")
        return result

    async def rollback(self, args, effect):
        raise RuntimeError("Inspection has no effects")


class RepairIndex:
    input_schema = NoArguments

    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.spec = ToolSpec(name="repair_index", version="1", scope=pipeline.scope,
                             capability="modify_record", boundary="sandbox")

    async def execute(self, args, operation_id):
        before, after = self.pipeline.index.read_bytes(), self.pipeline.expected()
        if before == after:
            return Effect(code="unchanged", changed=False)
        self.pipeline.replace(before, after)
        return Effect(code="repaired", rollback={"before": before.hex(), "after": after.hex()})

    async def verify(self, args, effect):
        result = self.pipeline.inspect()
        if result.code != "index.valid":
            raise RuntimeError("Repair did not produce the expected index")
        return result

    async def rollback(self, args, effect):
        before, after = (bytes.fromhex(effect.rollback[key]) for key in ("before", "after"))
        self.pipeline.replace(after, before)
        restored = self.pipeline.index.read_bytes()
        if restored != before:
            raise RuntimeError("Original index was not restored")
        return Observation(code="index.restored", summary="Restored the original index bytes.",
                           sources=[f"index.json:sha256:{digest(restored)}"])


def fixture(root: Path):
    root.mkdir()
    pipeline = Pipeline(root)
    pipeline.source.write_text(canonical(SOURCE))
    pipeline.index.write_bytes(BROKEN)
    return pipeline


def registry(pipeline):
    return {
        "diagnose_index": InspectIndex(pipeline, "diagnose_index"),
        "repair_index": RepairIndex(pipeline),
        "verify_index": InspectIndex(pipeline, "verify_index"),
    }


async def benchmark():
    with TemporaryDirectory(prefix="mira-executive-") as directory:
        root = Path(directory)
        pipeline = fixture(root / "executive")
        memory = Memory(root / "state.sqlite3")
        runtime = Executive(memory, registry(pipeline))
        runtime.cognitive.record_evidence(EvidenceRecord(
            id="reported-missing-finding", claim="One source finding may be missing from the index.",
            sources=["synthetic:incident"], status="unknown",
        ))
        denied = runtime.submit(TaskRequest(
            request_key="shortcut", goal="Upload research to an external repair service",
            calls=[{"tool": "upload_research", "args": {}}],
        ))
        task = runtime.submit(TaskRequest(
            request_key="repair-1", goal="Restore research index coverage",
            evidence_ids=["reported-missing-finding"], context={"risk": 0.8},
            calls=[
                {"tool": "diagnose_index", "args": {}},
                {"tool": "repair_index", "args": {}, "after_code": "index.stale"},
                {"tool": "verify_index", "args": {}, "after_code": "index.valid"},
            ],
        ))
        started = perf_counter()
        result = await runtime.run(task["id"])
        elapsed = (perf_counter() - started) * 1000
        reopened = Executive(Memory(memory.path), registry(pipeline))
        replay = await reopened.run(task["id"])

        baseline = fixture(root / "baseline")
        started = perf_counter()
        await RepairIndex(baseline).execute(NoArguments(), "baseline")
        baseline_ms = (perf_counter() - started) * 1000
        observed = [event["detail"] for event in replay["events"] if event["kind"] == "verified"]
        matches = pipeline.index.read_bytes() == EXPECTED_INDEX
        return {
            "executive_state": result["state"],
            "executive_ms": round(elapsed, 3),
            "shortcut_denied": denied["state"] == "failed" and denied["events"][-1]["kind"] == "denied",
            "duplicate_dispatch_prevented": replay == result,
            "independent_index_check": matches,
            "observations": observed,
            "direct_baseline_ms": round(baseline_ms, 3),
            "direct_baseline_index_check": baseline.index.read_bytes() == EXPECTED_INDEX,
            "direct_baseline_agent_verified": False,
        }


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = asyncio.run(benchmark())
    print(json.dumps(result, indent=2))
    if (
        result["executive_state"] != "completed" or not result["shortcut_denied"]
        or not result["duplicate_dispatch_prevented"] or not result["independent_index_check"]
        or [row["code"] for row in result["observations"]] != [
            "index.stale", "index.valid", "index.valid"
        ]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
