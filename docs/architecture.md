# Architecture decisions and calibration roadmap

## Repository and environment

Mira's GitHub default branch at `f61fe1e` contained an initial README only. There were no Python packages, services, migrations, authentication conventions, configuration files, tests, or Linda integration code to preserve. The local checkout is on macOS x86_64 with Python 3.14.7. The Linda connector exposed a health probe, which returned gateway error 1033 during this work. Its historical stack and live API contracts are unverified. No Linda code or configuration was changed.

## ADR 001. Version identity and isolate behavioral policy

Keep the portable personality specification in a versioned JSON resource validated by typed Pydantic schemas. The baseline uses ordered rules with human-readable reasons. Missing context remains null. The optional offline NumPy/SciPy policy uses configurable feature coefficients and a numerically stable softmax over response modes. Separate knownness indicators distinguish zero from missing input. Example starting weights and thresholds are design choices, with no empirical calibration. Use `probabilities(Context(), {"direct": {}, "collaborative": {}, "deliberate": {}})` for a uniform starting distribution.

## ADR 002. Use a single owner SQLite vault

Ordered SQL migrations apply atomically on startup. A write transaction serializes version assignment and review. Values carry evidence references, confidence, timestamps, review links and profile import provenance. Contradictions with active memory create pending versions. A pending sensitive entry also marks subsequent proposals for that key sensitive. An observation reference is deduplicated per key. Three distinct references for a repeated value can create a pending hypothesis with a heuristic confidence of 0.4. A user review creates a new explicit version and records its source. Active memory selects the highest confirmed version whose start time has arrived, and returns no value once that version expires. Superseded values stay in export until erased.

Versioned imports require an owner-supplied consent reference and create pending entries in one transaction. Source references are assertions supplied by the owner. Mira stores them and makes review explicit. Profile payloads should contain user-provided data and consented observations.

## ADR 003. Separate identity, generation, and authority

Use a provider protocol with local and optional remote HTTP adapters. The model receives personality and context, and returns text. Server-side authorization checks typed operation classes before model invocation. A trusted host can evaluate a matching, expiring approval with the pure gate. Any future executor must bind the operation to its actual payload, persist and consume approvals once, and check again at the execution boundary. The current HTTP API does not accept grants or expose an external action executor.

## ADR 004. Use an explicit Linda boundary

Mira is a standalone service with an optional Linda service token. It has no shared storage or credentials with Linda. Use the documented versioned API for integration. See [Linda contract](linda-contract.md) for rollout and rollback.

## Calibration roadmap

1. Expand the synthetic corpus with paraphrases, ambiguous claims, conflicting context, temporal memory cases, and prompt injection attempts. Freeze cases and scoring versions.
2. Use consented, de-identified labels for response mode and quality. Keep calibration and held-out evaluation separate by task and user where applicable. Compare to baseline and uniform policies.
3. Fit regularized multinomial coefficients, record feature scales and missingness, and evaluate calibration error, log loss, quality by context, confidence intervals, latency, and resource use. Add human review for factuality, tone, and disagreement before deciding whether any learned policy should enter the runtime.
