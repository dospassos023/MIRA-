from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class Provider(Protocol):
    async def complete(self, system: str, prompt: str) -> Completion: ...


class ProviderError(RuntimeError):
    pass


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
