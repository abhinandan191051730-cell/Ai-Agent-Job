import sqlite3
import os
from pathlib import Path
from datetime import datetime, date
from typing import Optional


class Database:
    def __init__(self, db_path: str = "./data/agent.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        return self.conn

    def initialize(self):
        schema_path = Path(__file__).parent / "schema.sql"
        conn = self.connect()
        conn.executescript(schema_path.read_text())
        conn.commit()

    def job_exists(self, unique_hash: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM jobs WHERE unique_hash = ?", (unique_hash,))
        return cur.fetchone() is not None

    def insert_job(self, job: dict) -> int:
        cur = self.conn.execute("""
            INSERT OR IGNORE INTO jobs (unique_hash, title, company, location, description, url, source, platform, salary_min, salary_max, posting_date, score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.get("unique_hash"), job.get("title"), job.get("company"),
            job.get("location"), job.get("description"), job.get("url"),
            job.get("source"), job.get("platform"), job.get("salary_min"),
            job.get("salary_max"), job.get("posting_date"), job.get("score", 0),
            job.get("status", "discovered")
        ))
        return cur.lastrowid or 0

    def update_job_status(self, job_id: int, status: str, score: float = None):
        if score is not None:
            self.conn.execute("UPDATE jobs SET status = ?, score = ?, updated_at = datetime('now') WHERE id = ?",
                              (status, score, job_id))
        else:
            self.conn.execute("UPDATE jobs SET status = ?, updated_at = datetime('now') WHERE id = ?",
                              (status, job_id))
        self.conn.commit()

    def log_application(self, job_id: int, status: str, score: float = None, platform: str = None, error: str = None):
        self.conn.execute("""
            INSERT INTO applications (job_id, status, score, platform, error_message, applied_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (job_id, status, score, platform, error))
        self.conn.commit()

    def check_rate_limit(self, platform: str, limit: int) -> bool:
        today = date.today().isoformat()
        cur = self.conn.execute(
            "SELECT count FROM rate_limits WHERE platform = ? AND date = ?", (platform, today))
        row = cur.fetchone()
        current = row["count"] if row else 0
        return current < limit

    def increment_rate_limit(self, platform: str):
        today = date.today().isoformat()
        self.conn.execute("""
            INSERT INTO rate_limits (platform, date, count) VALUES (?, ?, 1)
            ON CONFLICT(platform, date) DO UPDATE SET count = count + 1
        """, (platform, today))
        self.conn.commit()

    def get_stats(self) -> dict:
        conn = self.connect()
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'applied'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'failed'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'scored'").fetchone()[0]
        by_source = {}
        for row in conn.execute("SELECT source, COUNT(*) as cnt FROM jobs GROUP BY source"):
            by_source[row["source"]] = row["cnt"]
        return {
            "total_jobs": total,
            "applied": applied,
            "failed": failed,
            "pending": pending,
            "by_source": by_source,
        }

    def get_pending_jobs(self, min_score: float = 0) -> list:
        cur = self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'scored' AND score >= ? ORDER BY score DESC", (min_score,))
        return [dict(row) for row in cur.fetchall()]

    def get_failed_jobs(self) -> list:
        cur = self.conn.execute(
            "SELECT j.* FROM jobs j JOIN applications a ON j.id = a.job_id WHERE a.status = 'failed'")
        return [dict(row) for row in cur.fetchall()]

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
