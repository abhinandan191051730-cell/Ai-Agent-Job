#!/usr/bin/env python3
import os
import sys
import asyncio
import argparse
import uuid
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

from utils.logger import setup_logging, get_logger
from utils.browser import BrowserManager
from utils.retry import with_retry
from utils.exceptions import SelectorNotFoundError, AuthRequiredError
from core.profile import Profile
from core.config_models import ProfileConfig, SettingsConfig
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
from appliers.indeed import IndeedApplier
from appliers.generic import GenericApplier

logger = get_logger("main")

LOCK_FILE = Path("./data/agent.lock")


def _check_lock():
    if LOCK_FILE.exists():
        logger.warning("Lock file exists at %s — another run may be in progress. Use --force to override.", LOCK_FILE)
        return False
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.touch()
    return True


def _release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


class JobAgent:
    def __init__(self, settings_path: str = "./config/settings.yaml", profile_path: str = "./config/profile.yaml"):
        import yaml

        with open(settings_path) as f:
            raw_settings = yaml.safe_load(f)
        with open(profile_path) as f:
            raw_profile = yaml.safe_load(f)

        validated_settings = SettingsConfig.model_validate(raw_settings)
        validated_profile = ProfileConfig.model_validate(raw_profile)

        self.settings = raw_settings
        self.profile_loader = Profile(profile_path)
        self.profile = self.profile_loader.load()
        self.db = Database(self.settings.get("global", {}).get("data_dir", "./data") + "/agent.db")
        self.db.initialize()
        self.deduper = Deduper(self.db)
        self.scorer = Scorer(self.profile)
        self.answer_engine = AnswerEngine(self.settings, self.db)
        self.dry_run = self.settings.get("global", {}).get("dry_run", False)
        profile_dir = self.settings.get("global", {}).get("browser_profile", None)
        self.browser = BrowserManager(
            headless=self.settings.get("global", {}).get("headless", True),
            data_dir=profile_dir
        )
        self.appliers = {}
        self.captcha_counts = defaultdict(int)
        self.max_captcha = self.settings.get("global", {}).get("max_captcha_per_run", 3)
        self.auth_required_platforms = set()
        self.run_id = uuid.uuid4().hex[:12]

        log_file = self.settings.get("global", {}).get("log_file", "")
        if not log_file:
            data_dir = self.settings.get("global", {}).get("data_dir", "./data")
            log_file = f"{data_dir}/logs/agent.log"
        setup_logging("INFO", log_file)

        logger.info("Config validated: profile OK, settings OK")

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
                if getattr(scraper, "auth_required", False):
                    self.auth_required_platforms.add(name)
                    self.db.set_auth_required(name, True)
                    logger.warning("%s requires login — skipping scraping for this run", name)
                    continue
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
        skipped_count = 0
        failed_count = 0
        captcha_count = 0

        for job in jobs:
            if applied_count >= max_jobs:
                logger.info("Reached max jobs per run limit (%d)", max_jobs)
                break
            if job.get("score", 0) < min_score:
                continue
            platform = job.get("platform", "generic")

            if platform in self.auth_required_platforms:
                logger.info("Skipping %s on %s — auth required", job.get("title"), platform)
                skipped_count += 1
                continue

            if self.captcha_counts.get(platform, 0) >= self.max_captcha:
                logger.info("Skipping %s on %s — captcha threshold exceeded", job.get("title"), platform)
                skipped_count += 1
                continue

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
                status = result.get("status", "failed")

                if status == "captcha":
                    captcha_count += 1
                    self.captcha_counts[platform] += 1
                    self.db.increment_captcha(platform)
                    if self.captcha_counts[platform] >= self.max_captcha:
                        logger.warning("CAPTCHA threshold reached for %s (%d/%d), stopping further attempts",
                                       platform, self.captcha_counts[platform], self.max_captcha)

                self.db.log_application(
                    job_id=job.get("id"),
                    status=status,
                    score=job.get("score"),
                    platform=platform,
                    error=result.get("error"),
                )
                if status == "applied":
                    self.db.increment_rate_limit(platform)
                    applied_count += 1
                    self.db.update_job_status(job["id"], "applied")
                elif status == "failed":
                    failed_count += 1
                elif status == "skipped":
                    skipped_count += 1

                logger.info("Apply result for %s at %s: %s", job.get("title"), job.get("company"), status)
            except SelectorNotFoundError as e:
                logger.error("Selector breakage on %s: %s", platform, e)
                failed_count += 1
            except Exception as e:
                logger.error("Apply failed for %s at %s: %s", job.get("title"), job.get("company"), e)
                failed_count += 1
                self.db.log_application(
                    job_id=job.get("id"), status="failed", score=job.get("score"),
                    platform=platform, error=str(e))

        console.print(f"\n[bold green]Applied to {applied_count} jobs this run[/bold green]")
        self._save_summary(jobs, applied_count, skipped_count, failed_count, captcha_count)

    def _save_summary(self, all_jobs, applied, skipped, failed, captcha_blocked):
        by_platform = defaultdict(int)
        above = 0
        below = 0
        min_score = self.settings.get("scoring", {}).get("min_score_to_apply", 65)
        for j in all_jobs:
            platform = j.get("platform", "unknown")
            by_platform[platform] += 1
            score = j.get("score", 0)
            if score >= min_score:
                above += 1
            else:
                below += 1

        summary = {
            "run_id": self.run_id,
            "discovered": len(all_jobs),
            "scored_above_threshold": above,
            "scored_below_threshold": below,
            "applied": applied,
            "skipped": skipped,
            "failed": failed,
            "captcha_blocked": captcha_blocked,
            "auth_required": len(self.auth_required_platforms),
            "by_platform": dict(by_platform),
        }
        self.db.save_run_summary(summary)

        data_dir = self.settings.get("global", {}).get("data_dir", "./data")
        sum_dir = Path(data_dir) / "run_summaries"
        sum_dir.mkdir(parents=True, exist_ok=True)
        import json, datetime
        report = summary.copy()
        report["timestamp"] = datetime.datetime.now().isoformat()
        report["auth_required_platforms"] = list(self.auth_required_platforms)
        report["captcha_counts"] = dict(self.captcha_counts)
        (sum_dir / f"run_{self.run_id}.json").write_text(json.dumps(report, indent=2))

        self._notify(summary)

    def _notify(self, summary):
        notify = self.settings.get("notify", {})
        if not notify.get("enabled"):
            return
        try:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["Subject"] = f"Job Agent Run {self.run_id[:8]} — {summary['applied']} applied"
            msg["From"] = notify.get("from_addr", "")
            msg["To"] = notify.get("to_addr", "")
            body = (
                f"Discovered: {summary['discovered']}\n"
                f"Applied: {summary['applied']}\n"
                f"Skipped: {summary['skipped']}\n"
                f"Failed: {summary['failed']}\n"
                f"CAPTCHA blocked: {summary['captcha_blocked']}\n"
                f"Auth required: {summary['auth_required']}\n"
            )
            msg.set_content(body)
            with smtplib.SMTP(notify.get("smtp_host", ""), notify.get("smtp_port", 587)) as s:
                s.starttls()
                s.login(notify.get("smtp_user", ""), notify.get("smtp_pass", ""))
                s.send_message(msg)
            logger.info("Run summary email sent to %s", notify.get("to_addr", ""))
        except Exception as e:
            logger.error("Failed to send notification email: %s", e)

    def _get_applier(self, platform: str):
        if platform in self.appliers:
            return self.appliers[platform]
        dry = self.dry_run
        ae = self.answer_engine
        p = self.profile
        factory = {
            "linkedin": LinkedInApplier(self.browser, p, ae, dry),
            "naukri": NaukriApplier(self.browser, p, ae, dry),
            "instahyre": InstahyreApplier(self.browser, p, dry),
            "greenhouse": GreenhouseApplier(self.browser, p, ae, dry),
            "lever": LeverApplier(self.browser, p, ae, dry),
            "workday": WorkdayApplier(self.browser, p, ae, dry),
            "ashby": AshbyApplier(self.browser, p, ae, dry),
            "indeed": IndeedApplier(self.browser, p, dry),
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
                for src, cnt in sorted(v.items()):
                    table.add_row(f"Jobs from {src}", str(cnt))
            else:
                table.add_row(k.replace("_", " ").title(), str(v))

        auth_platforms = list(self.auth_required_platforms) if self.auth_required_platforms else []
        if auth_platforms:
            table.add_row("Platforms needing login", ", ".join(auth_platforms))
        console.print(table)


async def main():
    parser = argparse.ArgumentParser(description="AI Job Application Agent")
    parser.add_argument("--discover", action="store_true", help="Scrape and score jobs without applying")
    parser.add_argument("--apply", action="store_true", help="Run discovery then apply")
    parser.add_argument("--dry-run", action="store_true", help="Log what would be applied without submitting")
    parser.add_argument("--resume", action="store_true", help="Continue interrupted session")
    parser.add_argument("--status", action="store_true", help="Show stats from database")
    parser.add_argument("--force", action="store_true", help="Override lock file")
    parser.add_argument("--platforms", nargs="+", help="Platforms to target (linkedin, naukri, instahyre, indeed)")
    parser.add_argument("--login", nargs="+", default=None, help="Log into platforms in visible browser (linkedin, naukri, instahyre, indeed)")
    parser.add_argument("--profile", default="./config/profile.yaml", help="Path to profile YAML")
    parser.add_argument("--settings", default="./config/settings.yaml", help="Path to settings YAML")
    args = parser.parse_args()

    if not args.force and not _check_lock():
        sys.exit(1)

    try:
        agent = JobAgent(settings_path=args.settings, profile_path=args.profile)

        if args.dry_run:
            agent.dry_run = True

        if args.status:
            agent.print_status()
            return

        if args.login:
            login_urls = {
                "linkedin": "https://www.linkedin.com/login",
                "naukri": "https://www.naukri.com/nlogin/login",
                "instahyre": "https://www.instahyre.com/login",
                "indeed": "https://secure.indeed.com/auth",
            }
            agent.browser.headless = False
            ctx = await agent.browser.start()
            page = await ctx.new_page()
            paused = False
            for platform in args.login:
                url = login_urls.get(platform)
                if not url:
                    logger.warning("Unknown platform: %s", platform)
                    continue
                logger.info("Opening %s login page for %s — please log in manually", platform, url)
                await page.goto(url, wait_until="domcontentloaded")
                logger.info("Press Enter in the terminal after logging into %s...", platform)
                import msvcrt
                print(f"Log into {platform} in the browser window, then press Enter here...")
                while True:
                    if msvcrt.kbhit() and msvcrt.getch() == b'\r':
                        break
                    await asyncio.sleep(0.5)
                logger.info("Proceeding to next platform...")
            await agent.close()
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
    finally:
        _release_lock()


if __name__ == "__main__":
    asyncio.run(main())
