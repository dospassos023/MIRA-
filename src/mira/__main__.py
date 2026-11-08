"""Small terminal client for the local Mira API."""
import os
import sys

import httpx


def main():
    token = os.getenv("MIRA_OWNER_TOKEN", "")
    if len(token) < 32:
        print("Set MIRA_OWNER_TOKEN to the same owner token used by the API.", file=sys.stderr)
        return 2
    base = os.getenv("MIRA_API_URL", "http://127.0.0.1:8765").rstrip("/")
    session_id = None
    print("Mira is here. Type /quit to leave. Conversations stay in your local SQLite vault.")
    try:
        with httpx.Client(timeout=90, trust_env=False, headers={"Authorization": f"Bearer {token}"}) as client:
            while True:
                try:
                    message = input("You: ").strip()
                except EOFError:
                    break
                if message.casefold() in {"/quit", "/exit"}:
                    break
                if not message:
                    continue
                try:
                    response = client.post(base + "/v1/chat", json={"message": message, "session_id": session_id})
                    response.raise_for_status()
                    data = response.json()
                    session_id = data["session_id"]
                    print(f"Mira: {data['text']}\n[{data['status']}]")
                except httpx.HTTPStatusError as error:
                    try:
                        detail = error.response.json().get("detail", "Service request failed")
                    except (ValueError, AttributeError):
                        detail = "Service request failed"
                    print(f"Mira is unavailable: {detail}")
                except (httpx.HTTPError, KeyError, ValueError):
                    print("I couldn't reach the local Mira service. Check that it is running and try again.")
    except KeyboardInterrupt:
        print()
    print("Conversation closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
