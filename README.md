# Mira

Mira is a local Python backend for a portable collaboration identity, contextual response policy, and an owner-controlled SQLite memory vault. The API can run without a model. To generate text, configure a local Ollama model or opt in to the OpenAI API.

## Install and start

Python 3.12 or later is required. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[experimental,test]'
export MIRA_OWNER_TOKEN="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m uvicorn mira.api:create_app --factory --host 127.0.0.1 --port 8765 --no-access-log
```

For the base API without SciPy or test tools, use `python -m pip install .`. On Windows, activate with `.venv\Scripts\Activate.ps1` and set environment variables with `$env:NAME = "value"`. See [.env.example](.env.example) for configuration. Use a private directory for the database, with an owner-only ACL on Windows. Startup creates and migrates `data/mira.sqlite3` automatically.

In a second terminal with the same owner token:

```sh
curl -fsS http://127.0.0.1:8765/healthz
curl -fsS http://127.0.0.1:8765/v1/policy \
  -H "Authorization: Bearer $MIRA_OWNER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"urgency":0.8,"preferred_style":"concise"}'
curl -fsS http://127.0.0.1:8765/v1/memory \
  -H "Authorization: Bearer $MIRA_OWNER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"key":"reply.style","value":"concise","kind":"explicit","confidence":1,"evidence":[{"kind":"user_statement","reference":"my-preference-1"}]}'
python -m mira
```

The terminal chat keeps a local session, retrieves relevant confirmed nonsensitive memories with their evidence citations, applies Mira's deterministic response policy, and sends the turn to the configured model. It cannot run tools. Consequential work uses the separate persistent task API, which requires exact owner approval where its registered tool declares that requirement. Start with `python -m mira.sandbox` for the offline verified-action smoke demo; it uses only synthetic files.

The running API exposes OpenAPI and interactive docs at `/docs`. See the [Linda contract](docs/linda-contract.md) for permissions and payloads.

## Model providers

Set `MIRA_PROVIDER=ollama` and `MIRA_MODEL` to the exact name of an installed chat model. Start Ollama separately. Mira connects to the loopback address configured by `MIRA_OLLAMA_URL`. The default is `MIRA_PROVIDER=none`, which enables the API and memory vault but not generated conversation. Check `/v1/status` with the owner token to see the runtime configuration.

For the optional hosted adapter, set `MIRA_PROVIDER=openai`, `MIRA_MODEL`, and `OPENAI_API_KEY` in the process environment. The authenticated owner request and response context go to the configured model. This uses API billing. ChatGPT Plus is separate. Review the local model's license before distribution.

See [OpenAI Platform setup for MIRA](docs/openai-platform-setup.md) for project spend controls, secure key handling, identity behavior, and the current voice/MCP integration limits. No API key or paid request is needed to verify the identity bootstrap.

## Tests and evaluation

```sh
python -m pytest -q
python -m mira.evaluation
```

The fixture scorecard checks the harness with three synthetic scenarios repeated three times. Run `python -m mira.evaluation --provider` to score your configured model on the same synthetic inputs. This sends the synthetic prompts to that provider. It reports repeat consistency, exact expected claim coverage, disagreement stance, extra claim rate as a proxy for hallucination, and unscorable outputs. Exact claim matching can penalize paraphrases. Policy adaptation and preference alignment score the deterministic policy. Authorization and memory metrics are component checks. Latency measures provider calls. Token usage is reported when available, and `--price-per-million INPUT OUTPUT` computes estimated cost from supplied rates. Missing usage stays unknown.

See [architecture and roadmap](docs/architecture.md), [threat model](docs/threat-model.md), and [dependency inventory](docs/dependencies.md).

## Conversation and cognitive engine

The `/v1/chat` endpoint and `python -m mira` provide persistent local text conversation. The versioned expression identity in `src/mira/persona.json` and the style profile in `src/mira/personality.json` are both loaded into every text-model request; authorization remains separate in `src/mira/policy.py`. `/v1/identity` supplies the same persona to text and dedicated voice clients. The optional `/voice` page connects to OpenAI Realtime using a short-lived browser credential, but it is disabled unless explicitly enabled in the process environment. The deterministic workflow primitives, source-linked evidence ledger, risk-aware planning, observed outcome checks, rollback protocol, and feedback records are described in [MIRA Cognitive Engine v1](docs/cognitive-engine.md). The only supplied executor is the synthetic sandbox pipeline. No MCP server, public deployment, or Linda OS connection is verified or configured.

## Executive Runtime

Run `python -m mira.sandbox` for the offline research pipeline benchmark. Mira diagnoses a broken index, executes an authorized repair, verifies the outcome, and rejects an unregistered upload. See the [Executive Runtime contract](docs/executive-runtime.md) for task endpoints and adapter permissions.

The installation commands above work from a regular local checkout without a `PYTHONPATH` override.
