# Linda OS integration contract

Run Mira as a separate process. Configure `MIRA_LINDA_TOKEN` only when connecting a trusted client. Requests use `Authorization: Bearer <token>` and JSON. The owner and Linda tokens are separate. `GET /healthz` is public and returns basic liveness.

| Route | Access | Behavior |
| --- | --- | --- |
| `GET /v1/personality` | Owner or Linda | Versioned portable personality specification |
| `POST /v1/policy` | Owner or Linda | Context in, response mode, style and reasons out |
| `POST /v1/authorize` | Owner or Linda | Deterministic classification of a proposed operation |
| `POST /v1/respond` | Owner or Linda with local provider | Text and response metadata for an allowed operation. OpenAI is owner only. |
| `POST /v1/memory`, `GET /v1/memory/{key}` | Owner | Propose memory or read its current confirmed value |
| `POST /v1/observations`, `POST /v1/profiles` | Owner | Store a consented observation or import a pending profile |
| `POST /v1/memory/{key}/review` | Owner | Confirm a pending version or submit a correction |
| `GET /v1/memory` | Owner | Export versions, observations and import metadata |
| `DELETE /v1/memory/{key}`, `DELETE /v1/memory` | Owner | Erase a key or the vault contents with `X-Mira-Confirm: delete:<key>` or `delete-all` |

Example generation request:

```json
{
  "prompt": "Draft a two-step plan for the workshop.",
  "operation": {"id": "workshop-1", "action": "draft", "target": "local-draft"},
  "context": {"urgency": 0.8, "preferred_style": "concise"}
}
```

Omit unavailable context fields. Successful generation returns `text`, `policy`, `personality_version`, and `usage`. A missing credential gives 401, insufficient access or a consequential action gives 403, an invalid request gives 422, an unavailable model gives 503, and an upstream failure gives 502. Output is plain text for display or review. Linda must enforce its own authorization at action execution and pass only approved non-confidential inputs.

## Proposed rollout requiring Linda owner approval

1. Restore the gateway and inventory the actual Linda runtime, callers, credential store, logs, and records boundary. Identify the adapter location and validate the contract against a staging checkout using synthetic requests.
2. Present the exact staging patch and connectivity changes for approval. Prefer a same-host connection. If the services are on separate hosts, use authenticated private transport with TLS, request limits, and a scoped Linda token.
3. Enable read-only policy and text generation for synthetic data, check privilege separation and redaction, then decide whether to enable for approved users. Roll back by disabling the adapter and revoking the service token. The separate Mira vault has no Linda schema to roll back.
