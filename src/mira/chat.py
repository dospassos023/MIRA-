"""Persistent local conversation history and conservative evidence retrieval."""
from __future__ import annotations

import re
from uuid import uuid4

from .memory import Memory, now


class ChatSessions:
    def __init__(self, memory: Memory):
        self.memory = memory

    def retrieve(self, query: str, limit: int = 5) -> list[dict]:
        """Return only confirmed, current, nonsensitive memories with their citations."""
        terms = {word.casefold() for word in re.findall(r"[\w.-]{3,}", query)}
        if not terms:
            return []
        at = now()
        with self.memory.connect() as db:
            rows = db.execute(
                """SELECT key, value, confidence, evidence FROM memory_versions m
                   WHERE state='confirmed' AND sensitive=0
                   AND (valid_from IS NULL OR valid_from<=?)
                   AND (valid_until IS NULL OR valid_until>?)
                   AND version=(SELECT MAX(v.version) FROM memory_versions v
                                WHERE v.key=m.key AND v.state='confirmed'
                                AND (v.valid_from IS NULL OR v.valid_from<=?))""",
                (at, at, at),
            ).fetchall()
        ranked = []
        for row in rows:
            haystack = f"{row['key']} {row['value']}".casefold()
            score = sum(term in haystack for term in terms)
            if score:
                import json
                ranked.append((score, {"key": row["key"], "value": row["value"],
                                       "confidence": row["confidence"],
                                       "evidence": json.loads(row["evidence"])}))
        return [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["key"]))[:limit]]

    def history(self, session_id: str, limit: int = 12) -> list[dict]:
        with self.memory.connect() as db:
            if not db.execute("SELECT 1 FROM chat_sessions WHERE id=?", (session_id,)).fetchone():
                raise KeyError(session_id)
            return [dict(row) for row in db.execute(
                "SELECT role,content FROM chat_messages WHERE session_id=? ORDER BY sequence DESC LIMIT ?",
                (session_id, limit),
            )][::-1]

    def append(self, session_id: str | None, user: str, assistant: str) -> str:
        with self.memory.connect(write=True) as db:
            if session_id is None:
                session_id = str(uuid4())
                db.execute("INSERT INTO chat_sessions VALUES (?,?,?)", (session_id, now(), now()))
            elif not db.execute("SELECT 1 FROM chat_sessions WHERE id=?", (session_id,)).fetchone():
                raise KeyError(session_id)
            db.executemany(
                "INSERT INTO chat_messages(session_id,role,content,recorded_at) VALUES (?,?,?,?)",
                [(session_id, "user", user, now()), (session_id, "assistant", assistant, now())],
            )
            db.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now(), session_id))
        return session_id
