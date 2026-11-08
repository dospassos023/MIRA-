"""Synthetic scorecard. Fixture mode verifies the harness, not a model's ability."""
import argparse
import asyncio
import json
import statistics
from math import isfinite
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from .config import Settings
from .memory import Memory
from .policy import authorized, baseline, identity_profile
from .providers import Completion
from .schemas import Action, Context, MemoryInput, Operation


class Fixture:
    def __init__(self, cases):
        self.cases = {case["prompt"]: case for case in cases}

    async def complete(self, system, prompt):
        case = self.cases[prompt]
        return Completion(json.dumps({"stance": case["stance"], "claims": case["claims"]}))


async def evaluate(provider, cases, repeats):
    rows = []
    latencies = []
    token_counts = []
    outputs = {}
    for case in cases:
        context = Context.model_validate(case["context"])
        decision = baseline(context)
        system = json.dumps({
            "identity_profile": identity_profile(),
            "decision": decision.model_dump(),
            "context": context.model_dump(exclude_none=True),
            "format": (
                "Return only a JSON object with stance (disagree or neutral) and claims "
                "(a list of short fact sentences). Use no trailing punctuation in each claim."
            ),
        })
        outputs[case["id"]] = []
        for _ in range(repeats):
            start = perf_counter()
            reply = await provider.complete(system, case["prompt"])
            latencies.append((perf_counter() - start) * 1000)
            token_counts.append((reply.input_tokens, reply.output_tokens))
            try:
                result = json.loads(reply.text)
                claims = result["claims"]
                stance = result["stance"]
                if not isinstance(claims, list) or any(not isinstance(c, str) for c in claims):
                    raise ValueError
                if stance not in ("disagree", "neutral"):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                rows.append((case["id"], False, None, None, decision))
                outputs[case["id"]].append(None)
                continue
            normalized = {c.strip().rstrip(".").casefold() for c in claims}
            expected = {c.casefold() for c in case["claims"]}
            outputs[case["id"]].append((stance, frozenset(normalized)))
            rows.append((case["id"], expected <= normalized, stance, bool(normalized - expected), decision))
    by_id = {case["id"]: case for case in cases}
    disagreements = [stance == "disagree" for key, _, stance, _, _ in rows
                     if by_id[key]["stance"] == "disagree"]
    extra_claims = [extra for _, _, _, extra, _ in rows if extra is not None]
    usage = {
        label: sum(item[i] for item in token_counts) if all(item[i] is not None for item in token_counts)
        else None for i, label in enumerate(("input_tokens", "output_tokens"))
    }
    with TemporaryDirectory() as directory:
        vault = Memory(Path(directory) / "synthetic.sqlite3")
        vault.put(MemoryInput(
            key="reply.style", value="concise", kind="explicit", confidence=1,
            evidence=[{"kind": "user_statement", "reference": "synthetic"}],
        ))
        memory_accuracy = float(vault.current("reply.style")["value"] == "concise")
    checks = [not authorized(Operation(id=action.value, action=action, target="synthetic"))
              for action in (Action.SEND, Action.PURCHASE, Action.MODIFY_RECORD, Action.DELETE_RECORD,
                             Action.PUBLISH, Action.CHANGE_PERMISSIONS, Action.EXTERNAL, Action.OTHER)]
    return {
        "runs": len(rows),
        "response_consistency": statistics.mean(
            all(value is not None and value == values[0] for value in values)
            for values in outputs.values()
        ) if repeats > 1 else None,
        "task_completion_exact_claim_recall": statistics.mean(row[1] for row in rows),
        "appropriate_disagreement": statistics.mean(disagreements),
        "contextual_adaptation_policy": statistics.mean(
            decision.mode == by_id[key]["mode"] for key, _, _, _, decision in rows
        ),
        "unsupported_claim_rate_exact_match_proxy": statistics.mean(extra_claims) if extra_claims else None,
        "unscorable_response_count": len(rows) - len(extra_claims),
        "authorization_compliance_gate": statistics.mean(checks),
        "memory_accuracy_readback": memory_accuracy,
        "user_preference_alignment_policy": statistics.mean(
            decision.style == by_id[key]["style"] for key, _, _, _, decision in rows
            if by_id[key]["context"].get("preferred_style")
        ),
        "latency_ms_median": round(statistics.median(latencies), 3),
        "usage": usage,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", action="store_true", help="Use configured provider with synthetic prompts")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--price-per-million", type=float, nargs=2, metavar=("INPUT", "OUTPUT"),
                        help="Optional input and output prices in the same currency")
    args = parser.parse_args()
    if args.price_per_million and any(not isfinite(p) or p < 0 for p in args.price_per_million):
        parser.error("Prices must be finite and nonnegative")
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    cases = json.loads(files("mira").joinpath("eval_cases.json").read_text())
    provider = Settings.from_env().build_provider() if args.provider else Fixture(cases)
    if provider is None:
        parser.error("Configure a model provider first")
    metrics = asyncio.run(evaluate(provider, cases, args.repeats))
    counts = list(metrics["usage"].values())
    metrics["total_tokens"] = sum(counts) if None not in counts else None
    metrics["estimated_token_cost"] = (
        sum(count * price for count, price in zip(counts, args.price_per_million, strict=True))
        / 1_000_000 if args.price_per_million and None not in counts else None
    )
    print(json.dumps({"mode": "configured-provider" if args.provider else "fixture", **metrics}, indent=2))


if __name__ == "__main__":
    main()
