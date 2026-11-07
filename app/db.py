"""Tiny storage layer: SQLite by default, Postgres (e.g. Neon free tier) when
DATABASE_URL starts with postgres. Only synthetic / test data belongs here."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "asha_saathi.db")
_IS_PG = DATABASE_URL.startswith("postgres")
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS workers (
    id {pk},
    tg_hash TEXT UNIQUE,
    name TEXT,
    village TEXT,
    is_demo INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS beneficiaries (
    id {pk},
    worker_id INTEGER,
    kind TEXT,              -- mother / child
    name TEXT,
    village TEXT,
    lmp TEXT,               -- mothers
    dob TEXT,               -- children
    mother_id INTEGER,
    is_synthetic INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id {pk},
    beneficiary_id INTEGER,
    code TEXT,
    done_on TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS triage_log (
    id {pk},
    worker_id INTEGER,
    beneficiary_id INTEGER,
    level TEXT,
    signs TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS usage_log (
    id {pk},
    worker_id INTEGER,
    channel TEXT,
    intent TEXT,
    llm_used INTEGER DEFAULT 0,
    created_at TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_id(raw: str) -> str:
    """Telegram ids are stored only as salted hashes."""
    salt = os.environ.get("ID_SALT", "asha-saathi")
    return hashlib.sha256(f"{salt}:{raw}".encode()).hexdigest()[:24]


class DB:
    def __init__(self):
        if _IS_PG:
            import psycopg  # type: ignore
            self._pg = psycopg
            self.ph = "%s"
        else:
            self.ph = "?"
        self.init()

    @contextmanager
    def conn(self):
        if _IS_PG:
            c = self._pg.connect(DATABASE_URL, autocommit=True)
            try:
                yield c
            finally:
                c.close()
        else:
            with _lock:
                c = sqlite3.connect(SQLITE_PATH)
                c.row_factory = sqlite3.Row
                try:
                    yield c
                    c.commit()
                finally:
                    c.close()

    def init(self):
        pk = "SERIAL PRIMARY KEY" if _IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
        with self.conn() as c:
            for stmt in SCHEMA.format(pk=pk).split(";"):
                if stmt.strip():
                    c.execute(stmt)

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        sql = sql.replace("?", self.ph)
        with self.conn() as c:
            cur = c.execute(sql, args)
            if cur.description is None:
                return []
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def insert(self, table: str, **kw) -> int:
        kw.setdefault("created_at", now())
        cols = ",".join(kw)
        marks = ",".join([self.ph] * len(kw))
        with self.conn() as c:
            if _IS_PG:
                cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks}) RETURNING id", tuple(kw.values()))
                return cur.fetchone()[0]
            cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(kw.values()))
            return cur.lastrowid

    # ---- domain helpers -------------------------------------------------
    def worker(self, tg_raw: str, name: str = "", is_demo: int = 0) -> dict:
        h = hash_id(tg_raw)
        rows = self.q("SELECT * FROM workers WHERE tg_hash=?", (h,))
        if rows:
            return rows[0]
        wid = self.insert("workers", tg_hash=h, name=name, is_demo=is_demo)
        return self.q("SELECT * FROM workers WHERE id=?", (wid,))[0]

    def beneficiaries(self, worker_id: int) -> list[dict]:
        return self.q("SELECT * FROM beneficiaries WHERE worker_id=? ORDER BY id", (worker_id,))

    def find(self, worker_id: int, name: str) -> list[dict]:
        return self.q("SELECT * FROM beneficiaries WHERE worker_id=? AND lower(name) LIKE ? ORDER BY id",
                      (worker_id, f"%{name.lower()}%"))

    def done_map(self, beneficiary_id: int) -> dict[str, date]:
        rows = self.q("SELECT code, done_on FROM events WHERE beneficiary_id=?", (beneficiary_id,))
        return {r["code"]: date.fromisoformat(r["done_on"]) for r in rows}

    def log(self, worker_id: int | None, channel: str, intent: str, llm_used: bool = False):
        self.insert("usage_log", worker_id=worker_id, channel=channel, intent=intent, llm_used=int(llm_used))

    def stats(self) -> dict:
        one = lambda sql: list(self.q(sql)[0].values())[0]  # noqa: E731
        return {
            "workers_real": one("SELECT COUNT(*) FROM workers WHERE is_demo=0"),
            "workers_demo": one("SELECT COUNT(*) FROM workers WHERE is_demo=1"),
            "mothers": one("SELECT COUNT(*) FROM beneficiaries WHERE kind='mother'"),
            "children": one("SELECT COUNT(*) FROM beneficiaries WHERE kind='child'"),
            "events_recorded": one("SELECT COUNT(*) FROM events"),
            "triage_checks": one("SELECT COUNT(*) FROM triage_log"),
            "triage_red": one("SELECT COUNT(*) FROM triage_log WHERE level='RED'"),
            "messages": one("SELECT COUNT(*) FROM usage_log"),
            "messages_non_demo": one("SELECT COUNT(*) FROM usage_log u JOIN workers w ON u.worker_id=w.id WHERE w.is_demo=0"),
            "llm_calls": one("SELECT COUNT(*) FROM usage_log WHERE llm_used=1"),
        }
