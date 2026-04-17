"""Persistent history of folder-batch runs, stored in SQLite.

Schema:
    runs(id, created_at, path, model, total, done, status, settings_json, results_json)
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from .config import DATA_DIR

DB_PATH = DATA_DIR / "history.db"
_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                path TEXT NOT NULL,
                model TEXT,
                total INTEGER,
                done INTEGER,
                status TEXT,
                settings_json TEXT,
                results_json TEXT
            )
        """)
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC)"
        )
        _conn.commit()
    return _conn


def record_run(
    path: str,
    model: str,
    total: int,
    done: int,
    status: str,
    settings: dict,
    results: list,
) -> int:
    """插入一条 run 记录，返回 id。同一 path 的旧记录会被删除（覆盖语义）。"""
    with _lock:
        conn = _connection()
        conn.execute("DELETE FROM runs WHERE path = ?", (path,))
        cur = conn.execute(
            """INSERT INTO runs
               (created_at, path, model, total, done, status,
                settings_json, results_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _dt.datetime.now().isoformat(timespec="seconds"),
                path, model, total, done, status,
                json.dumps(settings, ensure_ascii=False),
                json.dumps(results, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_runs(limit: int = 200) -> List[dict]:
    """返回最新的 N 条 run 元数据（不含 results_json，避免过大）。
    settings_json 会被解析为 dict 返回。"""
    with _lock:
        rows = _connection().execute(
            """SELECT id, created_at, path, model, total, done, status,
                      settings_json
               FROM runs ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["settings"] = json.loads(d.pop("settings_json") or "{}")
        except Exception:
            d["settings"] = {}
            d.pop("settings_json", None)
        out.append(d)
    return out


def get_run(run_id: int) -> Optional[dict]:
    with _lock:
        row = _connection().execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["settings"] = json.loads(data.pop("settings_json") or "{}")
    data["results"] = json.loads(data.pop("results_json") or "[]")
    return data


def delete_run(run_id: int) -> bool:
    with _lock:
        cur = _connection().execute("DELETE FROM runs WHERE id = ?", (run_id,))
        _connection().commit()
        return cur.rowcount > 0
