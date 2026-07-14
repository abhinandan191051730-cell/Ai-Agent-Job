import re
from typing import Optional


class Scorer:
    def __init__(self, profile: dict):
        self.profile = profile

    def score(self, job: dict) -> float:
        title = (job.get("title") or "").lower()
        description = (job.get("description") or "").lower()
        location = (job.get("location") or "").lower()
        score = 0.0

        target_roles = [r.lower() for r in self.profile.get("target_roles", [])]
        skills = [s.lower() for s in self.profile.get("skills", [])]
        target_locations = [l.lower() for l in self.profile.get("target_locations", [])]

        if any(role in title for role in target_roles):
            score += 25

        if skills:
            matched_skills = sum(1 for s in skills if s in title or s in description)
            score += min(30, (matched_skills / max(len(skills), 1)) * 30)

        if "anywhere" in target_locations:
            score += 15
        elif target_locations:
            if any(loc in location for loc in target_locations):
                score += 15
            elif "remote" in location or "anywhere" in location:
                score += 10

        description_lower = description.lower()
        title_lower = title.lower()
        seniority_keywords = ["senior", "lead", "principal", "staff", "manager", "head"]
        has_senior = any(k in title_lower or k in description_lower for k in seniority_keywords)
        experience_items = self.profile.get("experience", [])
        years_exp = len(experience_items) * 2 if experience_items else 2
        if not has_senior or years_exp >= 5:
            score += 10

        fresh_keywords = ["urgent", "immediate", "new", "recent"]
        if any(k in description_lower for k in fresh_keywords):
            score += 10

        if description:
            word_count = len(description.split())
            if word_count > 100:
                score += 10

        return min(100.0, round(score, 1))
