# MIRA OpenAI Platform setup

MIRA keeps its identity/personality separate from permission policy. Text chat uses the configured model adapter; the dedicated browser voice page uses OpenAI Realtime over WebRTC. ChatGPT Voice remains a separate product and is not changed by this repository.

## What the project costs

The Platform's **Build $5** marker is a cumulative credit-purchase threshold for higher rate limits, not a MIRA project fee or a fixed API price. API use is billed by model and usage. The provided screenshots showed **$0.00 credit remaining** and no API requests, so a paid request cannot be verified from this checkout and likely requires adding billing/credits first. No credits, key, or API call were created here.

As of November 8, 2026, the official Standard API rate card lists `gpt-6-luna` at $0.10 per million input tokens and $0.50 per million output tokens. A text turn using 4,000 input and 1,000 output tokens would cost about $0.0009; 1,000 such turns would be about $0.90. Actual prompt size, response size, caching, model choice, and tools change the total. See the [OpenAI API pricing page](https://developers.openai.com/api/docs/pricing).

For low-latency voice, `gpt-realtime-2.1-mini` is listed at $10 per million input audio tokens and $20 per million output audio tokens. OpenAI estimates one input audio token per 100 ms and one output audio token per 50 ms. If a 10-minute daily conversation is split evenly between user speech and Mira speech for 30 days, the simple audio-only estimate is about $4.50/month, plus text/context usage. Silence is filtered by voice activity detection; long sessions can cost more as prior context is reused. See [Realtime pricing and cost guidance](https://developers.openai.com/api/docs/pricing) and [Realtime cost optimization](https://developers.openai.com/api/docs/guides/voice-latency-cost?voice-api=realtime).

The voice page caps each model response at 256 tokens and disconnects its own session after 10 minutes. Those are app-side safeguards, not an account-wide spend cap. Set a small Platform budget and alerts and check actual usage in the dashboard. Budget enforcement can lag; do not treat an alert or budget as a guaranteed exact ceiling.

## Safe activation

1. In the existing **M.I.R.A.** project, review **Billing → Overview → Usage limits** and **Usage**. Do not add credits or payment details unless you choose to fund the pilot.
2. If you decide to proceed, create a project-scoped API key in **M.I.R.A. → API Keys**. Store it in your local secret manager and inject it into the MIRA process as `OPENAI_API_KEY`. Never send the key in chat, add it to Git, or put it in screenshots.
3. Keep text-model use disabled unless separately configured. Dedicated voice is opt-in with `MIRA_REALTIME_ENABLED=true`; the default is off. The suggested model is `gpt-realtime-2.1-mini` and voice is `marin`.
4. Start MIRA bound to `127.0.0.1`, then open `http://127.0.0.1:8765/voice`. Enter the local MIRA owner token in the page and press **Start Mira voice**. The user action starts a billable voice session. The browser receives a 60-second ephemeral Realtime credential; the long-lived API key stays on the server. The page does not save transcripts and shows session token usage; reconcile dollars in OpenAI Usage.

An API key alone does not create billing credits. The `OPENAI_API_KEY` value must come from a secret manager or process environment. MIRA does not load `.env` files automatically.

## Current implementation and boundaries

- `/v1/identity?channel=text|voice` returns the same reviewed persona and identity contract without a model call.
- `/v1/chat` answers identity questions deterministically as Mira before a text model is configured; ordinary turns include the persona and personality on every model request.
- `/voice` is a dedicated local browser voice interface. Its Realtime session receives the same persona/personality, a fixed startup identity greeting instruction, no tools, and a 256-token per-response ceiling. The browser microphone and WebRTC session have not been exercised against a paid API account.
- The owner-authenticated secret endpoint is disabled by default. It returns only an ephemeral credential, model, voice, and expiry; it redacts provider errors.
- Voice transcripts are displayed in page memory only. Session token counts are not a persistent usage ledger; use the Platform Usage dashboard for billing reconciliation.
- Standard ChatGPT Voice is separate. This integration cannot enforce Mira's identity inside that product.
- MIRA has no MCP server, public deployment, or Linda OS connection. Voice has no external tools, and no legal-office records are involved.

## Local verification

The API tests use a mock HTTP transport. They verify authorization, request shape, identity/personality instructions, secret redaction, and the disabled-by-default setting without contacting OpenAI. Passing these tests does not verify microphone permissions, OpenAI account access, model availability for your project, billed audio quality, or actual Realtime behavior.
