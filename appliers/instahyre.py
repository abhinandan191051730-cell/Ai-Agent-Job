from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger
from utils.exceptions import SelectorNotFoundError

logger = get_logger("applier.instahyre")

CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
    "#captcha",
    ".g-recaptcha",
    "[data-sitekey]",
]


class InstahyreApplier:
    ELEMENT_TIMEOUT = 5000
    NAV_TIMEOUT = 30000

    def __init__(self, browser: BrowserManager, profile: dict, dry_run: bool = False):
        self.browser = browser
        self.profile = profile
        self.dry_run = dry_run

    async def apply(self, job: dict) -> dict:
        ctx = await self.browser.get_context()
        page = await ctx.new_page()
        result = {"status": "failed", "error": None}
        try:
            url = job.get("url", "")
            if not url:
                raise ValueError("No URL provided")

            logger.info("Instahyre: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(2, 4)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            if self.dry_run:
                logger.info("[DRY_RUN] Would apply to %s at %s via Instahyre", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            await self._click_interested_and_apply(page)
            result["status"] = "applied"
            logger.info("Applied to %s at %s via Instahyre", job.get("title"), job.get("company"))

        except Exception as e:
            result["error"] = str(e)
            logger.error("Instahyre apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _click_interested_and_apply(self, page):
        interested_selectors = ["#interested-btn", "button:has-text('Interested')", "[data-testid='interested-btn']"]
        apply_selectors = [
            "button.btn.btn-lg.btn-primary.new-btn",
            "button:has-text('Apply')",
            "[data-testid='apply-btn']",
        ]

        btn = await self._find_element(page, interested_selectors)
        if not btn:
            raise SelectorNotFoundError("Interested button", interested_selectors, page.url)
        await btn.click()
        await human_delay(1, 2)

        for _ in range(20):
            apply_btn = await self._find_element(page, apply_selectors)
            if not apply_btn:
                break
            await apply_btn.click()
            await human_delay(1, 2)

    async def _find_element(self, page, selectors: list):
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    return el
            except Exception:
                continue
        return None

    async def _detect_captcha(self, page) -> bool:
        for selector in CAPTCHA_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                return True
        return False
