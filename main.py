#!/usr/bin/env python3
import os
import sys
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from utils.logger import get_logger
from utils.browser import BrowserManager
from core.profile import Profile
from core.scorer import Scorer
from core.deduper import Deduper
from core.answer_engine import AnswerEngine
from state.db import Database
from scrapers.linkedin import LinkedInScraper
from scrapers.naukri import NaukriScraper
from scrapers.instahyre import InstahyreScraper
from scrapers.indeed import IndeedScraper
from scrapers.ats_detector import ATSDetector
from appliers.linkedin import LinkedInApplier
from appliers.naukri import NaukriApplier
from appliers.instahyre import InstahyreApplier
from appliers.greenhouse import GreenhouseApplier
from appliers.lever import LeverApplier
from appliers.workday import WorkdayApplier
from appliers.ashby import AshbyApplier
from appliers.generic import GenericApplier

logger = get_logger("main")


class JobAgent:
    def __init__(self, settings_path: str = "./config/settings.yaml", profile_path: str = "./config/profile.yaml"):
        import yaml
        with open(settings_path) as f:
            self.settings = yaml.safe_load(f)
        self.profile_loader = Profile(profile_path)
        self.profile = self.profile_loader.load()
        self.db = Database(self.settings.get("global", {}).get("data_dir", "./data") + "/agent.db")
        self.db.initialize()
        self.deduper = Deduper(self.db)
        self.scorer = Scorer(self.profile)
        self.answer_engine = AnswerEngine(self.settings, self.db)
        self.dry_run = self.settings.get("global", {}).get("dry_run", False)
        self.browser = BrowserManager(
            headless=self.settings.get("global", {}).get("headless", True),
            data_dir=self.settings.get("global", {}).get("data_dir", "./data") + "/browser_profile"
        )
        self.appliers = {}

    def _get_rate_limit(self, platform: str) -> int:
        return self.settings.get("rate_limits", {}).get(platform, 50)

    async def discover(self, platforms: list = None):
        await self.browser.start()
        all_jobs = []
        scrapers = {
            "linkedin": LinkedInScraper(self.browser),
            "naukri": NaukriScraper(self.browser),
            "instahyre": InstahyreScraper(self.browser),
            "indeed": IndeedScraper(self.browser),
        }
        targets = platforms or list(scrapers.keys())
        for name in targets:
            if name not in scrapers:
                continue
            try:
                scraper = scrapers[name]
                jobs = await scraper.search()
                for j in jobs:
                    if not self.deduper.is_duplicate(j):
                        jid = self.deduper.add_job(j)
                        j["id"] = jid
                        all_jobs.append(j)
                    else:
                        logger.debug("Duplicate skipped: %s at %s", j.get("title"), j.get("company"))
                logger.info("Discovered %d new jobs from %s", len(jobs), name)
            except Exception as e:
                logger.error("Scraper %s failed: %s", name, e)
        return all_jobs

    async def score_jobs(self, jobs: list):
        scored = []
        for job in jobs:
            try:
                score = self.scorer.score(job)
                job["score"] = score
                if job.get("id"):
                    self.db.update_job_status(job["id"], "scored", score)
                scored.append(job)
            except Exception as e:
                logger.error("Scoring failed for job %s: %s", job.get("title"), e)
        scored.sort(key=lambda x: x.get("score", 0), reverse=True)
        logger.info("Scored %d jobs", len(scored))
        return scored

    async def apply(self, jobs: list):
        if not jobs:
            logger.info("No jobs to apply to")
            return

        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title="Jobs to Apply")
        table.add_column("Score", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Company", style="yellow")
        table.add_column("Platform", style="blue")

        for j in jobs:
            table.add_row(str(j.get("score", 0)), j.get("title", ""), j.get("company", ""), j.get("platform", "generic"))
        console.print(table)

        min_score = self.settings.get("scoring", {}).get("min_score_to_apply", 65)
        max_jobs = self.settings.get("global", {}).get("max_jobs_per_run", 200)
        if self.dry_run:
            logger.info("DRY RUN mode - no applications will be submitted")

        applied_count = 0
        for job in jobs:
            if applied_count >= max_jobs:
                logger.info("Reached max jobs per run limit (%d)", max_jobs)
                break
            if job.get("score", 0) < min_score:
                continue
            platform = job.get("platform", "generic")
            limit = self._get_rate_limit(platform)
            if not self.db.check_rate_limit(platform, limit):
                logger.info("Rate limit reached for %s", platform)
                continue
            applier = self._get_applier(platform)
            if not applier:
                logger.warning("No applier for platform: %s", platform)
                continue
            try:
                result = await applier.apply(job)
                self.db.log_application(
                    job_id=job.get("id"),
                    status=result.get("status", "failed"),
                    score=job.get("score"),
                    platform=platform,
                    error=result.get("error"),
                )
                if result.get("status") == "applied":
                    self.db.increment_rate_limit(platform)
                    applied_count += 1
                    self.db.update_job_status(job["id"], "applied")
                logger.info("Apply result for %s at %s: %s", job.get("title"), job.get("company"), result.get("status"))
            except Exception as e:
                logger.error("Apply failed for %s at %s: %s", job.get("title"), job.get("company"), e)
                self.db.log_application(
                    job_id=job.get("id"), status="failed", score=job.get("score"),
                    platform=platform, error=str(e))

        console.print(f"\n[bold green]Applied to {applied_count} jobs this run[/bold green]")

    def _get_applier(self, platform: str):
        if platform in self.appliers:
            return self.appliers[platform]
        dry = self.dry_run
        ae = self.answer_engine
        p = self.profile
        factory = {
            "linkedin": LinkedInApplier(self.browser, p, dry),
            "naukri": NaukriApplier(self.browser, p, None, dry),
            "instahyre": InstahyreApplier(self.browser, p, dry),
            "greenhouse": GreenhouseApplier(self.browser, p, ae, dry),
            "lever": LeverApplier(self.browser, p, ae, dry),
            "workday": WorkdayApplier(self.browser, p, ae, dry),
            "ashby": AshbyApplier(self.browser, p, ae, dry),
            "generic": GenericApplier(self.browser, p, ae, dry),
        }
        applier = factory.get(platform, factory["generic"])
        self.appliers[platform] = applier
        return applier

    async def close(self):
        await self.browser.close()
        self.db.close()

    def print_status(self):
        stats = self.db.get_stats()
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="Application Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        for k, v in stats.items():
            if k == "by_source":
                for src, cnt in v.items():
                    table.add_row(f"Jobs from {src}", str(cnt))
            else:
                table.add_row(k.replace("_", " ").title(), str(v))
        console.print(table)


async def main():
    parser = argparse.ArgumentParser(description="AI Job Application Agent")
    parser.add_argument("--discover", action="store_true", help="Scrape and score jobs without applying")
    parser.add_argument("--apply", action="store_true", help="Run discovery then apply")
    parser.add_argument("--dry-run", action="store_true", help="Log what would be applied without submitting")
    parser.add_argument("--resume", action="store_true", help="Continue interrupted session")
    parser.add_argument("--status", action="store_true", help="Show stats from database")
    parser.add_argument("--platforms", nargs="+", help="Platforms to target (linkedin, naukri, instahyre, indeed)")
    parser.add_argument("--profile", default="./config/profile.yaml", help="Path to profile YAML")
    parser.add_argument("--settings", default="./config/settings.yaml", help="Path to settings YAML")
    args = parser.parse_args()

    agent = JobAgent(settings_path=args.settings, profile_path=args.profile)

    if args.dry_run:
        agent.dry_run = True

    if args.status:
        agent.print_status()
        return

    if args.resume:
        pending = agent.db.get_pending_jobs(agent.settings.get("scoring", {}).get("min_score_to_apply", 65))
        if pending:
            logger.info("Resuming with %d scored jobs from previous run", len(pending))
            await agent.browser.start()
            await agent.apply(pending)
        else:
            logger.info("No pending jobs to resume")
        await agent.close()
        return

    if args.discover or args.apply:
        jobs = await agent.discover(args.platforms)
        scored = await agent.score_jobs(jobs)
        if args.apply:
            await agent.apply(scored)
        else:
            from rich.console import Console
            console = Console()
            console.print(f"\n[bold]Discovered {len(jobs)} jobs, scored {len(scored)} above threshold[/bold]")
            for j in scored[:20]:
                console.print(f"  {j.get('score', 0):3.0f} | {j.get('title',''):40} | {j.get('company',''):25} | {j.get('platform','')}")
        await agent.close()
        return

    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
