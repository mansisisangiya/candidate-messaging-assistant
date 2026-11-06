"""SQLite persistence for agent runs and their steps (the only mutable state).

A new connection is opened per operation: SQLite connections are cheap, and this
avoids sharing one connection across FastAPI's worker threads.
"""
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.errors import RecordNotFoundError
from app.models import AgentRun, AgentStep, RunStatus, RunSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    status TEXT NOT NULL,
    instructions TEXT,
    draft_text TEXT,
    final_text TEXT,
    rejection_reason TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL REFERENCES runs(id),
    idx INTEGER NOT NULL,
    type TEXT NOT NULL,
    name TEXT,
    input TEXT,
    output TEXT,
    error TEXT,
    duration_ms INTEGER NOT NULL,
    ts TEXT NOT NULL,
    PRIMARY KEY (run_id, idx)
);
CREATE INDEX IF NOT EXISTS idx_runs_conversation ON runs(conversation_id, created_at);
"""

# Columns that may be written alongside a status change or on their own.
# Status itself is NOT here: it changes only via update_status_if, called by services/run_state.py.
_UPDATABLE = {"draft_text", "final_text", "rejection_reason", "error"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _dump(value: dict | None) -> str | None:
    return None if value is None else json.dumps(value)


def _load(value: str | None) -> dict | None:
    return None if value is None else json.loads(value)


class RunRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:  # commit on success, roll back on error
                yield conn
        finally:
            conn.close()

    def create_run(self, conversation_id: str, instructions: str | None = None) -> AgentRun:
        run_id, now = uuid.uuid4().hex, _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, conversation_id, status, instructions, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, conversation_id, RunStatus.RUNNING, instructions, now, now),
            )
        return self.get_run(run_id)

    def add_step(self, run_id: str, step: AgentStep) -> None:
        with self._connect() as conn:
            self._require_run(conn, run_id)
            conn.execute(
                "INSERT INTO steps (run_id, idx, type, name, input, output, error, duration_ms, ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, step.index, step.type, step.name, _dump(step.input),
                 _dump(step.output), step.error, step.duration_ms, step.ts.isoformat()),
            )
            conn.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), run_id))

    def update_run(self, run_id: str, **fields: str | None) -> AgentRun:
        """Update non-status columns."""
        self._check_fields(fields, allow_empty=False)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._connect() as conn:
            self._require_run(conn, run_id)
            conn.execute(
                f"UPDATE runs SET {assignments}, updated_at = ? WHERE id = ?",
                (*fields.values(), _now(), run_id),
            )
        return self.get_run(run_id)

    def update_status_if(
        self, run_id: str, expected: RunStatus, new: RunStatus, **fields: str | None
    ) -> bool:
        """Conditional write: change status (and fields) only if the row still has `expected`.

        Returns False when no row matched, i.e. the caller's view of the run was stale.
        """
        self._check_fields(fields, allow_empty=True)
        assignments = "".join(f", {name} = ?" for name in fields)
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE runs SET status = ?{assignments}, updated_at = ? WHERE id = ? AND status = ?",
                (new, *fields.values(), _now(), run_id, expected),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _check_fields(fields: dict[str, str | None], *, allow_empty: bool) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown or (not fields and not allow_empty):
            raise ValueError(f"cannot update fields: {sorted(unknown)}")

    def get_run(self, run_id: str) -> AgentRun:
        with self._connect() as conn:
            row = self._require_run(conn, run_id)
            step_rows = conn.execute(
                "SELECT * FROM steps WHERE run_id = ? ORDER BY idx", (run_id,)
            ).fetchall()
        return self._to_run(row, step_rows)

    def list_run_summaries(self, conversation_id: str | None = None) -> list[RunSummary]:
        """Newest first, without loading step rows."""
        where, params = ("WHERE r.conversation_id = ?", (conversation_id,)) if conversation_id \
            else ("", ())
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.*, (SELECT COUNT(*) FROM steps s WHERE s.run_id = r.id) AS step_count"
                f" FROM runs r {where} ORDER BY r.created_at DESC, r.rowid DESC", params
            ).fetchall()
        return [RunSummary(**dict(row)) for row in rows]

    def list_runs(self, conversation_id: str | None = None) -> list[AgentRun]:
        query, params = "SELECT id FROM runs", ()
        if conversation_id is not None:
            query, params = query + " WHERE conversation_id = ?", (conversation_id,)
        with self._connect() as conn:
            ids = [r["id"] for r in conn.execute(query + " ORDER BY created_at DESC, rowid DESC", params)]
        return [self.get_run(run_id) for run_id in ids]

    @staticmethod
    def _require_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise RecordNotFoundError(f"No run found with id '{run_id}'")
        return row

    @staticmethod
    def _to_run(row: sqlite3.Row, step_rows: list[sqlite3.Row]) -> AgentRun:
        steps = [
            AgentStep(
                index=s["idx"], type=s["type"], name=s["name"], input=_load(s["input"]),
                output=_load(s["output"]), error=s["error"], duration_ms=s["duration_ms"],
                ts=s["ts"],
            )
            for s in step_rows
        ]
        return AgentRun(
            id=row["id"], conversation_id=row["conversation_id"], status=row["status"],
            instructions=row["instructions"], steps=steps, draft_text=row["draft_text"],
            final_text=row["final_text"], rejection_reason=row["rejection_reason"],
            error=row["error"], created_at=row["created_at"], updated_at=row["updated_at"],
        )
