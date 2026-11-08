import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from .schemas import Evidence, MemoryInput, Observation, ProfileImport, Review


class Conflict(ValueError):
    pass


def timestamp(value=None):
    return value.astimezone(UTC).isoformat(timespec="microseconds") if value else None


def now():
    return timestamp(datetime.now(UTC))


class Memory:
    """A single personal vault. Each write has one SQLite transaction."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise PermissionError("Memory database cannot be a symlink")
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(fd)
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise PermissionError("Memory database must be private (chmod 600)")
        self.migrate()

    @contextmanager
    def connect(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self):
        migrations = sorted(
            (p for p in files("mira").joinpath("migrations").iterdir()
             if p.name.endswith(".sql")), key=lambda p: p.name
        )
        with self.connect(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
            applied = {row[0] for row in db.execute("SELECT name FROM schema_migrations")}
            names = [item.name for item in migrations]
            if applied != set(names[:len(applied)]):
                raise RuntimeError("Incompatible database migration history")
            for migration in migrations[len(applied):]:
                # Execute one statement at a time to preserve the enclosing transaction.
                statement = ""
                for line in migration.read_text().splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        db.execute(statement)
                        statement = ""
                if statement.strip():
                    raise RuntimeError(f"Incomplete migration {migration.name}")
                db.execute("INSERT INTO schema_migrations VALUES (?)", (migration.name,))

    @staticmethod
    def _row(row):
        result = dict(row)
        result["evidence"] = json.loads(result["evidence"])
        result["sensitive"] = bool(result["sensitive"])
        return result

    @staticmethod
    def _current(db, key, at):
        return db.execute(
            """SELECT * FROM memory_versions WHERE key = ? AND state = 'confirmed'
               AND (valid_from IS NULL OR valid_from <= ?)
               ORDER BY version DESC LIMIT 1""", (key, at)
        ).fetchone()

    def _insert(self, db, entry, *, profile=None, review=None):
        at = now()
        version = db.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM memory_versions WHERE key = ?",
            (entry.key,),
        ).fetchone()[0]
        current = self._current(db, entry.key, at)
        active = current and (not current["valid_until"] or current["valid_until"] > at)
        conflict = current["version"] if active and current["value"] != entry.value else None
        sensitive = entry.sensitive or bool(db.execute(
            "SELECT 1 FROM memory_versions WHERE key = ? AND sensitive = 1 LIMIT 1",
            (entry.key,),
        ).fetchone())
        pending = review is None and (
            profile or sensitive or entry.kind == "hypothesis" or conflict
        )
        state = "pending" if pending else "confirmed"
        result = db.execute(
            """INSERT INTO memory_versions
               (key, version, value, kind, confidence, sensitive, evidence, state,
                contradicts_version, reviewed_from, valid_from, valid_until, created_at,
                profile_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
            (entry.key, version, entry.value, entry.kind, entry.confidence,
             sensitive,
             json.dumps([item.model_dump() for item in entry.evidence]), state, conflict,
             review, timestamp(entry.valid_from), timestamp(entry.valid_until), at, profile),
        ).fetchone()
        return self._row(result)

    def put(self, entry: MemoryInput):
        with self.connect(write=True) as db:
            return self._insert(db, entry)

    def review(self, key: str, review: Review):
        with self.connect(write=True) as db:
            source = db.execute(
                "SELECT * FROM memory_versions WHERE key = ? AND version = ?",
                (key, review.version),
            ).fetchone()
            if source is None:
                raise KeyError(key)
            latest_confirmed = db.execute(
                "SELECT MAX(version) FROM memory_versions WHERE key = ? AND state = 'confirmed'",
                (key,),
            ).fetchone()[0] or 0
            if source["state"] == "superseded" or source["version"] < latest_confirmed:
                raise Conflict("That version is stale")
            if source["state"] == "confirmed" and review.corrected_value is None:
                raise Conflict("That version is already confirmed")
            data = self._row(source)
            entry = MemoryInput(
                key=key, value=review.corrected_value or data["value"], kind="explicit",
                sensitive=data["sensitive"], confidence=1.0,
                evidence=[*data["evidence"][:29], Evidence(
                    kind="user_statement", reference=review.evidence_reference
                )],
                valid_from=data["valid_from"], valid_until=data["valid_until"],
            )
            if entry.valid_until and timestamp(entry.valid_until) <= now():
                raise Conflict("That version has expired")
            updated = self._insert(db, entry, profile=data["profile_version"], review=review.version)
            if source["state"] == "pending":
                db.execute(
                    "UPDATE memory_versions SET state = 'superseded' WHERE key = ? AND version = ?",
                    (key, review.version),
                )
            return updated

    def observe(self, observation: Observation):
        with self.connect(write=True) as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO observations VALUES (?, ?, ?, ?)",
                (observation.key, observation.value, observation.reference, now()),
            ).rowcount
            if not inserted:
                existing = db.execute(
                    "SELECT value FROM observations WHERE key = ? AND reference = ?",
                    (observation.key, observation.reference),
                ).fetchone()
                if existing["value"] != observation.value:
                    raise Conflict("Observation reference already has a different value")
                return None
            matches = db.execute(
                """SELECT reference FROM observations WHERE key = ? AND value = ?
                   ORDER BY observed_at, reference LIMIT 3""",
                (observation.key, observation.value),
            ).fetchall()
            if len(matches) < 3 or db.execute(
                "SELECT 1 FROM memory_versions WHERE key = ? AND value = ?",
                (observation.key, observation.value),
            ).fetchone():
                return None
            return self._insert(db, MemoryInput(
                key=observation.key, value=observation.value, kind="hypothesis",
                confidence=0.4, evidence=[
                    Evidence(kind="observed_pattern", reference=row["reference"])
                    for row in matches
                ],
            ))

    def import_profile(self, profile: ProfileImport):
        with self.connect(write=True) as db:
            if not db.execute(
                "INSERT OR IGNORE INTO profile_imports VALUES (?, ?, ?, ?)",
                (profile.profile_version, profile.schema_version, profile.consent_reference, now()),
            ).rowcount:
                raise Conflict("Profile version already exists")
            return [self._insert(db, entry, profile=profile.profile_version)
                    for entry in profile.entries]

    def current(self, key: str):
        at = now()
        with self.connect() as db:
            row = self._current(db, key, at)
            if row is None or (row["valid_until"] and row["valid_until"] <= at):
                raise KeyError(key)
            return self._row(row)

    def export(self):
        with self.connect() as db:
            return {
                "schema_version": 1,
                "memory": [self._row(row) for row in db.execute(
                    "SELECT * FROM memory_versions ORDER BY key, version"
                )],
                "observations": [dict(row) for row in db.execute(
                    "SELECT * FROM observations ORDER BY key, reference"
                )],
                "profiles": [dict(row) for row in db.execute(
                    "SELECT * FROM profile_imports ORDER BY profile_version"
                )],
            }

    def delete(self, key: str | None):
        with self.connect(write=True) as db:
            if key is None:
                db.execute("DELETE FROM memory_versions")
                db.execute("DELETE FROM observations")
            else:
                db.execute("DELETE FROM memory_versions WHERE key = ?", (key,))
                db.execute("DELETE FROM observations WHERE key = ?", (key,))
            db.execute(
                """DELETE FROM profile_imports WHERE NOT EXISTS (
                   SELECT 1 FROM memory_versions WHERE profile_version = profile_imports.profile_version
                )"""
            )
