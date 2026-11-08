# MIRA OpenAI Platform setup

MIRA keeps its identity/personality separate from permission policy. Text chat uses the configured model adapter; the dedicated browser voice page uses OpenAI Realtime over WebRTC. ChatGPT Voice remains a separate product and is not changed by this repository.

## What the project costs

The Platform's **Build $5** marker is a cumulative credit-purchase threshold for higher rate limits, not a MIRA project fee or a fixed API price. API use is billed by model and usage. The provided screenshots showed **$0.00 credit remaining** and no API requests, so a paid request cannot be verified from this checkout and likely requires adding billing/credits first. No credits, key, or API call were created here.

As of November 8, 2026, the official Standard API rate card lists `gpt-6-luna` at $0.10 per million input tokens and $0.50 per million output tokens. A text turn using 4,000 input and 1,000 output tokens would cost about $0.0009; 1,000 such turns would be about $0.90. Actual prompt size, response size, caching, model choice, and tools change the total. See the [OpenAI API pricing page](https://developers.openai.com/api/docs/pricing).

For low-latency voice, `gpt-realtime-2.1-mini` is listed at $10 per million input audio tokens and $20 per million output audio tokens. OpenAI estimates one input audio token per 100 ms and one output audio token per 50 ms. If a 10-minute daily conversation is split evenly between user speech and Mira speech for 30 days, the simple audio-only estimate is about $4.50/month, plus text/context usage. Silence is filtered by voice activity detection; long sessions can cost more as prior context is reused. See [Realtime pricing and cost guidance](https://developers.openai.com/api/docs/pricing) and [Realtime cost optimization](https://developers.openai.com/api/docs/guides/voice-latency-cost?voice-api=realtime).

The voice page requests a 256-token response ceiling and closes the connection after 10 minutes. For a monthly cap on this project's API traffic, enable the Platform's hard spend limit. Alerts send notifications while traffic continues. The hard limit can take time to apply, so actual spend can be slightly higher. [OpenAI spend limits](https://developers.openai.com/api/docs/guides/spend-limits)

## Safe activation

1. Select the existing **M.I.R.A.** project and open **Settings → Limits**. If you see **Spend**, choose **Edit spend limit**, set your monthly amount, turn on **Enforce a hard limit**, and save. The supplied screenshot only shows model and rate controls. If **Spend** is absent, check **Organization settings → Billing → Overview → Usage limits** for the controls your account has. An organization cap applies to all its projects. [OpenAI spend limits](https://developers.openai.com/api/docs/guides/spend-limits)
2. In project **Settings → General**, keep **Standard** as the default tier. Under **Limits → Model usage**, allow the models you plan to use, such as `gpt-6-luna` for text and `gpt-realtime-2.1-mini` for voice, if listed. Add spend alerts to catch usage before the cap.
3. If you choose to fund the pilot, use **Organization settings → Billing → Overview** to review the credit purchase. In **M.I.R.A. → API Keys**, create a key scoped to this project. Use your local secret manager to supply it to the MIRA process as `OPENAI_API_KEY`. Keep it out of chat, source control, and screenshots. [OpenAI API keys](https://developers.openai.com/api/docs/guides/api-keys)
4. For text, set `MIRA_PROVIDER=openai` and `MIRA_MODEL=gpt-6-luna`. For voice, set `MIRA_REALTIME_ENABLED=true`. The voice defaults are `gpt-realtime-2.1-mini` and `marin`. Both OpenAI paths are off by default.
5. Start MIRA bound to `127.0.0.1`, then open `http://127.0.0.1:8765/voice`. Enter the local MIRA owner token and press **Start Mira voice** when ready for billable use. The browser receives a temporary Realtime credential. The API key stays on the server.
6. In the Platform **Usage** dashboard, filter to **M.I.R.A.** and compare billed usage with the browser's session token count.

An API key alone does not create billing credits. The `OPENAI_API_KEY` value must come from a secret manager or process environment. MIRA does not load `.env` files automatically.

## Current implementation and boundaries

- `/v1/identity?channel=text|voice` returns the same reviewed persona and identity contract without a model call.
- Both text endpoints answer direct identity questions as Mira without a model call. Ordinary turns include the persona and personality on every model request.
- `/voice` is a dedicated local browser voice interface. Its Realtime session receives the same persona/personality, a fixed startup identity greeting instruction, no tools, and a 256-token per-response ceiling. The browser microphone and WebRTC session have not been exercised against a paid API account.
- The owner-authenticated secret endpoint is disabled by default. It returns only an ephemeral credential, model, voice, and expiry; it redacts provider errors.
- Voice transcripts are displayed in page memory only. Session token counts are not a persistent usage ledger; use the Platform Usage dashboard for billing reconciliation.
- Standard ChatGPT Voice is separate. This integration cannot enforce Mira's identity inside that product.
- MIRA has no MCP server, public deployment, or Linda OS connection. Voice has no external tools, and no legal-office records are involved.

## Local verification

The Python suite uses a mock HTTP transport to verify authorization, request shape, identity instructions, secret redaction, and the disabled-by-default setting. Run `node --test tests/voice.test.mjs` to test greeting requests and cancellation with simulated microphone and network responses. A live check still needs microphone permission, project access, and an approved API test.
