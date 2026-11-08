from datetime import UTC, datetime
from importlib.resources import files
from typing import Literal

from .schemas import Action, Approval, Context, Operation, Persona, Personality, Schema

SAFE = frozenset({
    Action.ANALYZE, Action.RESEARCH, Action.PLAN, Action.COMPARE,
    Action.RECOMMEND, Action.DRAFT, Action.CALCULATE,
})
MODES = ("direct", "collaborative", "deliberate")
Mode = Literal["direct", "collaborative", "deliberate"]


class Decision(Schema):
    mode: Mode
    style: Literal["concise", "standard", "detailed"]
    reasons: list[str]


PERSONALITY = Personality.model_validate_json(files("mira").joinpath("personality.json").read_text())
PERSONA = Persona.model_validate_json(files("mira").joinpath("persona.json").read_text())


def identity_profile() -> dict:
    """The versioned expression identity, separate from the authority policy."""
    return {"persona": PERSONA.model_dump(), "personality": PERSONALITY.model_dump()}


def authorized(operation: Operation, *, trusted_approval: Approval | None = None) -> bool:
    """Only trusted host code may supply an approval. It must match this exact operation."""
    return operation.action in SAFE or (
        trusted_approval is not None
        and trusted_approval.operation == operation
        and trusted_approval.expires_at > datetime.now(UTC)
    )


def baseline(context: Context) -> Decision:
    if context.reversible is False or (context.risk is not None and context.risk >= 0.7):
        mode, reason = "deliberate", "Reported risk or irreversibility calls for checking assumptions."
    elif (
        (context.urgency is not None and context.urgency >= 0.7)
        or (context.deadline_hours is not None and context.deadline_hours <= 4)
        or (context.reported_fatigue is not None and context.reported_fatigue >= 0.7)
    ):
        mode, reason = "direct", "Reported urgency, deadline proximity, or fatigue favors fewer steps."
    elif context.strategic_relevance is not None and context.strategic_relevance >= 0.7:
        mode, reason = "deliberate", "Reported strategic relevance favors explicit tradeoffs."
    else:
        mode, reason = "collaborative", "Explore the problem with the user."
    reasons = [reason]
    if context.workload is not None and context.workload >= 0.7:
        reasons.append("Break the workload into manageable steps.")
    if context.available_resources == []:
        reasons.append("No resources were reported as available. Identify what is needed.")
    return Decision(mode=mode, style=context.preferred_style or (
        "concise" if mode == "direct" else "standard"
    ), reasons=reasons)
