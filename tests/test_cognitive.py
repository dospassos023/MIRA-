import asyncio
import json
from importlib.resources import files

import pytest

from mira.cognitive import CognitiveEngine, EvidenceRecord, Step, ToolOutcome
from mira.memory import Memory
from mira.schemas import Context, Operation


class Executor:
    def __init__(self, outcomes): self.outcomes, self.calls, self.rollbacks = outcomes, [], []
    async def execute(self, operation): self.calls.append(operation); return self.outcomes.pop(0)
    async def rollback(self, token):
        self.rollbacks.append(token); return ToolOutcome(success=True, observed=True, summary="restored")


@pytest.fixture
def engine(tmp_path): return CognitiveEngine(Memory(tmp_path / "memory.sqlite3"))


@pytest.mark.parametrize("round_id, expected", [(1,"challenge"),(2,"warmth"),(3,"proportionate"),(4,"investigate"),(5,"bounded"),(6,"flag")])
def test_six_approved_simulation_scenarios(round_id, expected):
    persona = json.loads(files("mira").joinpath("persona.json").read_text(encoding="utf-8"))
    rules = " ".join(persona["principles"]).lower()
    matched = {1:"challenge claims", 2:"vulnerability", 3:"human agency", 4:"preferred conclusion", 5:"proactively", 6:"flag material risks"}
    assert matched[round_id] in rules


def test_evidence_ledger_tracks_uncertainty_and_conflict(engine):
    a = EvidenceRecord(id="a", claim="effect exists", status="supported", confidence=.7, sources=["paper-a"])
    b = EvidenceRecord(id="b", claim="effect absent", status="disputed", confidence=.4, sources=["paper-b"])
    engine.record_evidence(a); engine.record_evidence(b)
    assert engine.evidence("a").sources == ["paper-a"]
    assert engine.assess([a,b])["contradiction"]
    assert engine.assess([EvidenceRecord(id="u", claim="unknown")])["uncertain"]


def test_unauthorized_operation_escalates(engine):
    op = Operation(id="publish-1", action="publish", target="paper")
    ex = Executor([])
    result = asyncio.run(engine.run("publish", [Step(description="publish", operation=op)], ex, Context()))
    assert result.state == "escalated" and not ex.calls


def test_unobserved_tool_outcome_never_claims_success(engine):
    op = Operation(id="draft-1", action="draft", target="local")
    ex = Executor([ToolOutcome(success=True, observed=False, summary="done", rollback_token="r1")])
    result = asyncio.run(engine.run("draft", [Step(description="draft", operation=op)], ex, Context()))
    assert result.state == "rolled_back" and ex.rollbacks == ["r1"]


def test_failed_rollback_escalates_as_failure(engine):
    class Broken(Executor):
        async def rollback(self, token): return ToolOutcome(success=False, observed=False, summary="could not restore")
    op = Operation(id="draft-2", action="draft", target="local")
    result = asyncio.run(engine.run("draft", [Step(description="draft", operation=op)], Broken([ToolOutcome(success=True, observed=False, summary="unknown", rollback_token="r")]), Context()))
    assert result.state == "failed"


def test_scientific_integrity_and_risk_inserts_assessment_step(engine):
    steps = engine.plan("analyze", [Step(description="compare studies")], Context(risk=.9))
    assert "evidence" in steps[0].description
    records = [EvidenceRecord(id="s", claim="supports H", status="supported", confidence=.8), EvidenceRecord(id="d", claim="opposes H", status="disputed", confidence=.8)]
    assert engine.assess(records)["contradiction"]


def test_feedback_is_attached_to_run(engine):
    op = Operation(id="calc", action="calculate", target="local")
    ex = Executor([ToolOutcome(success=True, observed=True, summary="calculated", evidence=["result-check"])])
    result = asyncio.run(engine.run("calculate", [Step(description="calculate", operation=op)], ex, Context()))
    engine.feedback(result.run_id, "verified against source")
    with engine.memory.connect() as db:
        assert db.execute("SELECT feedback FROM cognitive_runs WHERE id=?", (result.run_id,)).fetchone()[0] == "verified against source"
