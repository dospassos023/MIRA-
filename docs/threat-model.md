# Threat model

| Risk | Current boundary |
| --- | --- |
| Prompt injection or model overreach | Model text has no tool access. Deterministic gates precede generation and deny requests classified as consequential. Caller-supplied action labels do not authorize downstream execution. |
| Linda credential exposure or lateral movement | Separate tokens. Linda cannot access memory routes or the OpenAI provider. Revoke access by removing or rotating the token and restarting. |
| Poisoned memory | Owner-only writes, source references, version history and review for contradictions, hypotheses, imports and sensitive keys. Sensitivity and the authenticity of submitted evidence depend on the owner. |
| Personal or legal data leakage | Dedicated vault. Only an active, nonsensitive `reply.style` enum can affect the owner's local generation by default. Linda callers must exclude confidential records. OpenAI receives owner-supplied prompt and context when explicitly configured. |
| Token or payload logging | Uvicorn access logs are disabled in the documented command. Validation and provider errors omit request bodies, credentials and upstream text. Responses are marked no-store. Keep request and response body logging disabled at proxies. |
| Local file exposure | Private database file on POSIX. Restrict the directory and backup permissions. SQLite is plaintext and depends on OS access control and disk encryption for data at rest. Windows deployments need an owner-only directory ACL. |
| Data retention after erasure | Delete removes live versions and observations and unused profile imports. SQLite secure deletion is enabled. Exports, filesystem snapshots and backups need separate retention and deletion. |
| Denial of service | Bind to loopback, restrict provider endpoints, validate field sizes and use provider timeouts. Add body size limits, rate limits and transport security before offering network access. |

The trust boundary includes the host OS, Mira process, owner client and the configured model runtime. The vault is single owner. Keep deployment logs limited to status and timing, with no prompts, memory contents, access tokens, or source references.
