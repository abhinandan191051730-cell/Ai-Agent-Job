import hashlib
import json
from state.db import Database


class Deduper:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def make_hash(job: dict) -> str:
        raw = f"{job.get('title','')}|{job.get('company','')}|{job.get('url','')}|{job.get('description','')}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def is_duplicate(self, job: dict) -> bool:
        h = self.make_hash(job)
        return self.db.job_exists(h)

    def add_job(self, job: dict) -> int:
        h = self.make_hash(job)
        job["unique_hash"] = h
        return self.db.insert_job(job)
