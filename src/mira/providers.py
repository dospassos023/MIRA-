from dataclasses import dataclass
from typing import Protocol

import httpx
import hashlib


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class Provider(Protocol):
    async def complete(self, system: str, prompt: str) -> Completion: ...


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealtimeClientSecret:
    value: str
    expires_at: int


class RealtimeProvider:
    """Mints short-lived browser credentials without exposing the API key."""

    endpoint = "https://api.openai.com/v1/realtime/client_secrets"

    def __init__(self, api_key: str, model: str, voice: str = "marin"):
        self.api_key = api_key
        self.model = model
        self.voice = voice

    async def create_client_secret(self, instructions: str, owner_token: str) -> RealtimeClientSecret:
        safety_id = hashlib.sha256(("mira-owner:" + owner_token).encode()).hexdigest()
        payload = {
            "expires_after": {"anchor": "created_at", "seconds": 60},
            "session": {
                "type": "realtime",
                "model": self.model,
                "instructions": instructions,
                "output_modalities": ["audio"],
                "max_output_tokens": 256,
                "tool_choice": "none",
                "tools": [],
                "audio": {"output": {"voice": self.voice}},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "OpenAI-Safety-Identifier": safety_id,
                    },
                )
                response.raise_for_status()
            data = response.json()
            value = data["value"]
            expires_at = data["expires_at"]
            if (
                not isinstance(value, str) or not value.startswith("ek_")
                or len(value) > 512 or not value.isascii()
                or type(expires_at) is not int or expires_at <= 0
            ):
                raise ValueError("Invalid client secret response")
            return RealtimeClientSecret(value=value, expires_at=expires_at)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError("Realtime client credential request failed") from None


class ChatProvider:
    def __init__(self, endpoint: str, model: str, *, api_key: str | None = None):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key

    async def complete(self, system: str, prompt: str) -> Completion:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        payload = {"model": self.model, "messages": messages, "stream": False}
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            payload["max_completion_tokens"] = 1024
        else:
            payload["options"] = {"num_predict": 1024}
        try:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
                response.raise_for_status()
            data = response.json()
            if self.api_key:
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                counts = usage.get("prompt_tokens"), usage.get("completion_tokens")
            else:
                content = data["message"]["content"]
                counts = data.get("prompt_eval_count"), data.get("eval_count")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Missing text")
            return Completion(content, *(
                count if type(count) is int and count >= 0 else None for count in counts
            ))
        except (httpx.HTTPError, ValueError, KeyError, IndexError, AttributeError, TypeError):
            raise ProviderError("Model provider request failed") from None
