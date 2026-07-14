import re
from urllib.parse import urlparse
from utils.browser import BrowserManager
from utils.logger import get_logger

logger = get_logger("scraper.ats_detector")


class ATSDetector:
    PATTERNS = {
        "greenhouse": ["boards.greenhouse.io", "greenhouse.io"],
        "lever": ["jobs.lever.co", "lever.co"],
        "workday": ["myworkdayjobs.com", "wd5.myworkdayjobs.com", "workday.com"],
        "ashby": ["jobs.ashbyhq.com", "ashbyhq.com"],
        "jobvite": ["jobs.jobvite.com", "jobvite.com"],
        "icims": ["icims.com", "jobs.icims.com"],
        "bamboohr": ["bamboohr.com", "apply.bamboohr.com"],
        "smartrecruiters": ["smartrecruiters.com"],
    }

    @staticmethod
    def detect_from_url(url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        for platform, domains in ATSDetector.PATTERNS.items():
            for d in domains:
                if d in domain:
                    return platform
        return "generic"

    @staticmethod
    async def detect_from_page(browser: BrowserManager, url: str) -> str:
        url_match = ATSDetector.detect_from_url(url)
        if url_match != "generic":
            return url_match
        ctx = await browser.get_context()
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            content = await page.content()
            lower = content.lower()
            if "greenhouse" in lower or "boards.greenhouse" in lower:
                return "greenhouse"
            if "lever" in lower and "jobs.lever" in lower:
                return "lever"
            if "workday" in lower or "myworkdayjobs" in lower:
                return "workday"
            if "ashby" in lower or "jobs.ashbyhq" in lower:
                return "ashby"
            if "jobvite" in lower:
                return "jobvite"
            if "icims" in lower:
                return "icims"
            if "bamboohr" in lower:
                return "bamboohr"
            if "smartrecruiters" in lower:
                return "smartrecruiters"
        except Exception as e:
            logger.debug("ATS detection failed for %s: %s", url, e)
        finally:
            await page.close()
        return "generic"
