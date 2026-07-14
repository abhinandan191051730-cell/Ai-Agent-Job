import os
import hashlib
import json
from typing import Optional
from state.db import Database


class AnswerEngine:
    def __init__(self, settings: dict, db: Optional[Database] = None):
        self.settings = settings
        self.db = db
        self.provider = settings.get("llm", {}).get("provider", "openai")
        self.model = settings.get("llm", {}).get("model", "gpt-4")
        self.temperature = settings.get("llm", {}).get("temperature", 0.3)
        self.max_tokens = settings.get("llm", {}).get("max_tokens", 2000)
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = os.getenv("LLM_API_KEY") or os.getenv(f"{self.provider.upper()}_API_KEY") or ""
        if self.provider == "openai":
            import openai
            self._client = openai.OpenAI(api_key=api_key)
        elif self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
        elif self.provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._client = genai
        elif self.provider == "ollama":
            from openai import OpenAI
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self._client = OpenAI(base_url=f"{base_url}/v1", api_key="ollama")
        else:
            import openai
            self._client = openai.OpenAI(api_key=api_key)
        return self._client

    def _cache_key(self, prompt: str) -> str:
        raw = f"{self.provider}:{self.model}:{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _check_cache(self, key: str) -> Optional[str]:
        if self.db is None:
            return None
        conn = self.db.connect()
        cur = conn.execute("SELECT response FROM llm_cache WHERE cache_key = ?", (key,))
        row = cur.fetchone()
        return row["response"] if row else None

    def _write_cache(self, key: str, response: str):
        if self.db is None:
            return
        conn = self.db.connect()
        conn.execute(
            "INSERT OR IGNORE INTO llm_cache (cache_key, response, model) VALUES (?, ?, ?)",
            (key, response, self.model))
        conn.commit()

    def ask(self, prompt: str, system: str = None, use_cache: bool = True) -> str:
        if use_cache:
            key = self._cache_key(prompt)
            cached = self._check_cache(key)
            if cached:
                return cached
        client = self._get_client()
        try:
            if self.provider == "anthropic":
                messages = []
                if system:
                    messages.append({"role": "user", "content": f"{system}\n\n{prompt}"})
                else:
                    messages.append({"role": "user", "content": prompt})
                resp = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    messages=messages
                )
                result = resp.content[0].text if resp.content else ""
            elif self.provider == "google":
                model = client.GenerativeModel(self.model)
                full_prompt = f"{system}\n\n{prompt}" if system else prompt
                resp = model.generate_content(full_prompt)
                result = resp.text
            else:
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                result = resp.choices[0].message.content or ""
        except Exception as e:
            result = f"Error generating answer: {e}"

        if use_cache and not result.startswith("Error"):
            self._write_cache(key, result)
        return result

    def generate_cover_letter(self, job: dict, profile: dict) -> str:
        prompt = (
            f"Write a concise, professional cover letter for the role '{job.get('title')}' "
            f"at {job.get('company')}.\n\nJob Description:\n{job.get('description', 'N/A')}\n\n"
            f"My background:\n{json.dumps(profile.get('experience', []), indent=2)}\n"
            f"Skills: {', '.join(profile.get('skills', []))}\n\n"
            f"Keep it under 300 words. Address it to the hiring manager."
        )
        return self.ask(prompt)

    def answer_screening(self, question: str, profile: dict) -> str:
        prompt = (
            f"Answer this job application screening question based on my profile.\n"
            f"Question: {question}\n\n"
            f"Profile: {json.dumps(profile, indent=2)}\n\n"
            f"Provide a concise, truthful answer."
        )
        return self.ask(prompt)
