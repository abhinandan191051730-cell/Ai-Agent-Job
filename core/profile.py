import yaml
from pathlib import Path
from typing import Optional


class Profile:
    def __init__(self, path: str = "./config/profile.yaml"):
        self.path = Path(path)
        self.data: dict = {}

    def load(self) -> dict:
        if not self.path.exists():
            raise FileNotFoundError(f"Profile not found at {self.path}")
        with open(self.path, "r") as f:
            self.data = yaml.safe_load(f) or {}
        return self.data

    def get(self, key: str, default=None):
        keys = key.split(".")
        val = self.data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default
