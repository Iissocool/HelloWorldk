from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import DATA_ROOT
from .models import ExecutionResult


DB_PATH = DATA_ROOT / "history.sqlite3"


@dataclass(slots=True)
class JobRecord:
    id: int
    created_at: str
    job_type: str
    backend: str
    model: str
    input_ref: str
    output_ref: str
    ok: bool
    return_code: int
    summary: str
    stdout: str
    stderr: str
    report_path: str


class HistoryStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_ref TEXT NOT NULL,
                    output_ref TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    return_code INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    stdout TEXT NOT NULL,
                    stderr TEXT NOT NULL,
                    report_path TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def add_job(
        self,
        *,
        job_type: str,
        backend: str,
        model: str,
        input_ref: str,
        output_ref: str,
        result: ExecutionResult,
    ) -> int:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_history (
                    created_at, job_type, backend, model, input_ref, output_ref,
                    ok, return_code, summary, stdout, stderr, report_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    job_type,
                    backend,
                    model,
                    input_ref,
                    output_ref,
                    1 if result.ok else 0,
                    result.return_code,
                    result.summary or "",
                    result.stdout or "",
                    result.stderr or "",
                    result.report_path or "",
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_recent(self, limit: int = 200) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            JobRecord(
                id=row["id"],
                created_at=row["created_at"],
                job_type=row["job_type"],
                backend=row["backend"],
                model=row["model"],
                input_ref=row["input_ref"],
                output_ref=row["output_ref"],
                ok=bool(row["ok"]),
                return_code=row["return_code"],
                summary=row["summary"],
                stdout=row["stdout"],
                stderr=row["stderr"],
                report_path=row["report_path"],
            )
            for row in rows
        ]

    def get(self, job_id: int) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM job_history WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return JobRecord(
            id=row["id"],
            created_at=row["created_at"],
            job_type=row["job_type"],
            backend=row["backend"],
            model=row["model"],
            input_ref=row["input_ref"],
            output_ref=row["output_ref"],
            ok=bool(row["ok"]),
            return_code=row["return_code"],
            summary=row["summary"],
            stdout=row["stdout"],
            stderr=row["stderr"],
            report_path=row["report_path"],
        )
