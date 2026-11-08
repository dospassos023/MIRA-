import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .providers import ChatProvider


@dataclass(frozen=True)
class Settings:
    owner_token: str = field(repr=False)
    memory_path: Path = Path("data/mira.sqlite3")
    linda_token: str | None = field(default=None, repr=False)
    provider: str = "none"
    model: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    openai_key: str | None = field(default=None, repr=False)

    def __post_init__(self):
        tokens = [t for t in (self.owner_token, self.linda_token) if t is not None]
        if any(len(t) < 32 or not t.isascii() or not t.isalnum() for t in tokens):
            raise ValueError("Use separate alphanumeric tokens of at least 32 characters")
        if self.owner_token == self.linda_token:
            raise ValueError("Owner and Linda tokens must differ")
        if self.provider not in {"none", "ollama", "openai"}:
            raise ValueError("Unsupported MIRA_PROVIDER")
        if self.provider != "none" and not self.model:
            raise ValueError("Set MIRA_MODEL for the selected provider")
        if self.provider == "openai" and not self.openai_key:
            raise ValueError("Set OPENAI_API_KEY for OpenAI")
        if self.provider == "ollama":
            url = urlsplit(self.ollama_url)
            if (
                url.scheme not in {"http", "https"}
                or url.hostname not in {"127.0.0.1", "::1"}
                or url.username is not None or url.password is not None
                or url.path not in {"", "/"} or url.query or url.fragment
                or not url.port
            ):
                raise ValueError("Use a loopback IP and explicit port for Ollama")

    @classmethod
    def from_env(cls):
        return cls(
            owner_token=os.getenv("MIRA_OWNER_TOKEN", ""),
            linda_token=os.getenv("MIRA_LINDA_TOKEN"),
            memory_path=Path(os.getenv("MIRA_DB_PATH", "data/mira.sqlite3")),
            provider=os.getenv("MIRA_PROVIDER", "none"),
            model=os.getenv("MIRA_MODEL"),
            ollama_url=os.getenv("MIRA_OLLAMA_URL", "http://127.0.0.1:11434"),
            openai_key=os.getenv("OPENAI_API_KEY"),
        )

    def build_provider(self):
        if self.provider == "ollama":
            return ChatProvider(self.ollama_url.rstrip("/") + "/api/chat", self.model)
        if self.provider == "openai":
            return ChatProvider(
                "https://api.openai.com/v1/chat/completions", self.model, api_key=self.openai_key
            )
        return None
