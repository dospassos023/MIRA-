# Executive Runtime v1

The owner submits a structured task containing proposed calls, context, and optional evidence IDs. The cognitive engine resolves the evidence and records a risk-sensitive plan. Each call resolves to a registered adapter with a typed input schema. A call can require a specific observation code from the previous verified call, allowing a diagnosis to select an authorized repair branch. Model-generated text carries no execution authority.

## State and authority

| State | Meaning |
| --- | --- |
| Queued | Ready for a worker claim |
| Awaiting approval | Held until the owner approves the exact persisted plan |
| Running | Claimed transactionally. Dispatch IDs and attempts are recorded before adapter invocation. |
| Completed | Each dispatched action returned a structured observation with sources |
| Failed | Denied, unverified, or interrupted. The escalation flag identifies outcomes that need reconciliation. |
| Rolled back | A failed workflow's known reversible effects were restored and restoration was observed |

Each adapter declares a version, capability, resource scope, permission boundary, timeout and retry limit. Register trusted code at startup via `create_app(settings, tools=registry)`. The default API factory has an empty registry. Keep the resource scope stable and specific to the adapter's configured destination or workspace. Changes in destination, effective behavior, or input semantics require a new scope or version. Arguments must include operation-specific targets and payload identifiers where relevant. Adapters independently validate inputs and enforce their declared boundaries. This is an in-process protocol for trusted adapters.

Purchases, external messages, confidential transfers, and consequential modifications always require approval. Sandbox writes are allowed only for adapters restricted to disposable, isolated state. An unregistered adapter or invalid arguments are denied. A pending task has no side effects. The authenticated owner approves a digest covering the task-specific plan, adapter scope/version and validated arguments. The approval expires, is consumed at the worker claim, and is checked again before every consequential dispatch or retry. A compensating consequential action requires separate authorization.

A repeated request key with identical content returns the original task. A different payload using that key returns a conflict. A single running task per vault and stable dispatch IDs prevent a second worker from executing the same task. Adapters may retry only after proving no effect and should propagate dispatch IDs to downstream idempotency mechanisms when available. Verification must read or query actual state and return evidence. Only verified observations support completion. Timeouts apply to cooperative async adapters, and blocking or detached work is outside the adapter contract.

A known failure can trigger verified compensation in reverse order. An ambiguous timeout, crash, or failed rollback requires reconciliation. The runtime never automatically replays an ambiguous dispatch. After confirming a worker has stopped and the running task is overdue, an owner can mark it failed for reconciliation. Inspect its events and the underlying resource before deciding whether to submit a new task. Task and evidence records are stored in the private SQLite vault and are separate from the personal preference export and deletion routes. Keep secrets and confidential records out of task payloads and evidence references.

## Owner API

| Method and path | Purpose |
| --- | --- |
| `GET /v1/tools` | Inspect available adapter contracts and input schemas |
| `POST /v1/tasks` | Submit `request_key`, `goal`, `calls`, optional `context` and `evidence_ids` |
| `GET /v1/tasks/{id}` | Read the plan, digest, state, escalation and chronological events |
| `POST /v1/tasks/{id}/approval` | Approve a pending `digest` with optional `ttl_seconds` |
| `POST /v1/tasks/{id}/run` | Claim a queued task and return its resulting state |
| `POST /v1/tasks/{id}/recover?worker_stopped=worker-stopped` | Reconcile an overdue task after confirming its worker has stopped |

A call has `tool`, `args`, and optional `after_code`. Inspect the returned state even on HTTP success. Linda credentials cannot use these routes.

## Reproduce the sandbox benchmark

```sh
python -m mira.sandbox
python -m pytest -q -W error
```

The fixture starts with two research findings and an index containing one. Mira refuses an unregistered upload shortcut, reads the index, gates repair on the stale diagnosis, rebuilds the file, and verifies the exact bytes and their hashes. The benchmark reopens the task database to check that the same request is never dispatched again. A direct repair on a separate identical fixture provides a timing and correctness baseline. The baseline is a bare adapter call with an independent benchmark check. It does not produce a durable plan or runtime verification record.

This benchmark measures one synthetic operational scenario. The larger Evaluation Laboratory and live Linda pilot follow this sprint. No network tools or office records participate in the benchmark.
