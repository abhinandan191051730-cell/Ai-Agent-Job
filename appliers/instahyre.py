from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("applier.instahyre")


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
        view_selector = "#interested-btn"
        try:
            await page.wait_for_selector(view_selector, timeout=5000)
            await page.locator(view_selector).nth(0).click()
            await human_delay(1, 2)

            apply_selector = "button.btn.btn-lg.btn-primary.new-btn"
            apply_count = 0

            while True:
                count = await page.locator(apply_selector).count()
                if count == 0:
                    break
                await page.locator(apply_selector).click()
                apply_count += 1
                await human_delay(1, 2)

            logger.info("Applied to %d job(s) via Instahyre", apply_count)

        except Exception as e:
            logger.debug("Instahyre apply interaction: %s", e)
            raise
