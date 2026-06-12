from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import HISTORY_DB_PATH


class JsonLineStore:
    """SQLite-backed run history store.

    The class name stays for backward compatibility with existing imports, but
    records are no longer appended to a shared JSONL file.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or HISTORY_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    risk_level TEXT,
                    route_json TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL
                )
                '''
            )
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agent_runs_session_created ON agent_runs(session_id, created_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at)')

    def ready(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute('SELECT 1')
            return True
        except sqlite3.Error:
            return False

    def append(self, record: dict) -> None:
        response = record.get('response') or {}
        request = record.get('request') or {}
        route = response.get('route') or []
        risk_level = None
        mfg = response.get('manufacturing_context') or {}
        if isinstance(mfg, dict):
            risk_level = ((mfg.get('risk_assessment') or {}).get('overall_priority'))
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT OR REPLACE INTO agent_runs
                (run_id, session_id, created_at, risk_level, route_json, request_json, response_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    record.get('run_id'),
                    record.get('session_id'),
                    datetime.now(timezone.utc).isoformat(),
                    risk_level,
                    json.dumps(route, ensure_ascii=False, default=str),
                    json.dumps(request, ensure_ascii=False, default=str),
                    json.dumps(response, ensure_ascii=False, default=str),
                ),
            )

    def list(self, limit: int = 50) -> list[dict]:
        limit = min(max(int(limit or 50), 1), 500)
        with self._connect() as conn:
            rows = conn.execute(
                '''
                SELECT run_id, session_id, created_at, risk_level, route_json, request_json, response_json
                FROM agent_runs
                ORDER BY created_at DESC
                LIMIT ?
                ''',
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                '''
                SELECT run_id, session_id, created_at, risk_level, route_json, request_json, response_json
                FROM agent_runs
                WHERE run_id = ?
                ''',
                (run_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict:
        return {
            'run_id': row['run_id'],
            'session_id': row['session_id'],
            'created_at': row['created_at'],
            'risk_level': row['risk_level'],
            'route': json.loads(row['route_json']),
            'request': json.loads(row['request_json']),
            'response': json.loads(row['response_json']),
        }
