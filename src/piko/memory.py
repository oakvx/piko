"""Local SQLite session and audit event ledger (no screenshots or input text)."""
import json
import sqlite3
from pathlib import Path

from piko.contracts import Event, Session, SessionState, now


class LocalMemory:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
            INSERT INTO schema_version(version)
              SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, data TEXT NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
              type TEXT NOT NULL, timestamp TEXT NOT NULL, payload TEXT NOT NULL
            );
        """)
        self.connection.commit()
        # Treat interrupted work as failed, never resume actions automatically.
        interrupted = (SessionState.OBSERVING, SessionState.ANALYZING,
                       SessionState.PLANNING, SessionState.EXECUTING,
                       SessionState.VERIFYING, SessionState.PAUSED)
        for row in self.connection.execute("SELECT data FROM sessions"):
            session = Session.model_validate_json(row[0])
            if session.state in interrupted:
                session.state = SessionState.FAILED
                session.error = "Application restarted; execution not automatically resumed"
                session.updated_at = now()
                self.save(session)

    def save(self, session: Session) -> None:
        # Avoid storing model-proposed typed text in the plan ledger.
        data = session.model_dump(mode="json", exclude={"plan"})
        self.connection.execute(
            "INSERT INTO sessions (id, data, state, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, state=excluded.state, updated_at=excluded.updated_at",
            (session.id, json.dumps(data), session.state.value, session.updated_at.isoformat()),
        )
        self.connection.commit()

    def write_event(self, event: Event) -> None:
        # Never include sensitive action text or a screenshot in event payloads.
        safe = {k: v for k, v in event.payload.items() if k in {"state", "action", "index", "reason", "verified"}}
        self.connection.execute(
            "INSERT INTO events (session_id, type, timestamp, payload) VALUES (?, ?, ?, ?)",
            (event.session_id, event.type, event.timestamp.isoformat(), json.dumps(safe)),
        )
        self.connection.commit()

    def list_sessions(self) -> list[Session]:
        return [Session.model_validate_json(r[0]) for r in self.connection.execute(
            "SELECT data FROM sessions ORDER BY updated_at DESC LIMIT 100")]

    def list_events(self, session_id: str) -> list[dict]:
        return [dict(type=row[0], timestamp=row[1], payload=json.loads(row[2])) for row in
                self.connection.execute("SELECT type,timestamp,payload FROM events WHERE session_id=? ORDER BY id", (session_id,))]

    def close(self) -> None:
        self.connection.close()
