# MIRA OpenAI Platform setup

This repository has an optional OpenAI **text** adapter. It does not contain an audio transport, realtime voice client, MCP server, or hosted deployment. `GET /v1/identity?channel=voice` is a bootstrap contract for a future dedicated client; it does not provide speech input or output. Regular ChatGPT Voice is a separate product and is not redirected by configuring this backend.

## Platform steps

Proceed one screen at a time. No key, billing change, or API request is needed for the first step.

1. Use the existing **M.I.R.A.** project; do not create a duplicate. Project **Settings → Limits** currently shows model access and request-rate settings. For budget controls, open **Billing → Overview → Usage limits** (the tile marked “Set monthly budgets”). Do not create a key or add credits until those budget controls are reviewed. Project and organization spend controls are available to eligible owners; where offered, enable a hard limit as well as alerts. OpenAI notes enforcement is not instantaneous, so a small overage is possible. These controls govern API spend and do not guarantee zero overage. See [OpenAI project limits](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform).

After the project exists, verify model access and limits in that project's settings. Usage can be reviewed by project in the Usage Dashboard and exported for reconciliation; API token counts are returned by this backend when the provider returns them. See [OpenAI usage dashboard](https://help.openai.com/en/articles/10478918-api-usage-dashboard).

## When explicitly ready to create a key

Create a project-scoped key from the **MIRA** project. Store it in your local secret manager or inject it into the process environment as `OPENAI_API_KEY`; never put the key in chat, source control, screenshots, or `.env.example`. The existing configuration reads the key from the environment and marks it non-repr so ordinary settings output does not disclose it. `.env` is ignored by Git, but an OS secret store is preferable.

Before enabling paid requests, set `MIRA_PROVIDER=openai`, choose an API model ID in `MIRA_MODEL`, and provide `OPENAI_API_KEY` through your secret manager. The current OpenAI adapter is the Chat Completions text endpoint, limits generation to 1,024 tokens, and sends the authenticated user's prompt and relevant request context to OpenAI. Do not send confidential or legal-office data unless that transfer is separately authorized and appropriately controlled.

The app has no in-process dollar budget or monthly usage ledger yet. Its response includes input/output token usage when supplied by the provider; missing usage is reported as unknown (identity bootstrap reports zero because it makes no provider call). Rely on the project's enforced hard limit and verify usage in the dashboard before enabling any paid call. No API call was made during local verification.

## Local verification

With no API key and `MIRA_PROVIDER=none`, the authenticated text endpoint `/v1/chat` answers identity questions with a fixed, truthful introduction. A dedicated text or voice client can fetch `/v1/identity?channel=text` or `/v1/identity?channel=voice`; both return the same identity contract. These checks do not establish a working audio interface or alter ChatGPT Voice behavior.
