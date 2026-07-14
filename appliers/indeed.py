from pathlib import Path
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger
from utils.exceptions import SelectorNotFoundError

logger = get_logger("applier.indeed")

APPLY_BUTTON_SELECTORS = [
    "button#indeedApplyButton",
    "button[id*='indeedApply']",
    ".jobsearch-IndeedApplyButton-newDesign",
    "button[aria-label*='Apply now']",
    "button:has-text('Apply now')",
]

CONTINUE_SELECTORS = [
    "button.ia-continueButton",
    "button[aria-label*='Continue']",
    "button[id*='continue']",
]

SUBMIT_SELECTORS = [
    "button[aria-label*='Submit']",
    "button.ia-continueButton[type='submit']",
    "button[id*='submit']",
]

FIELD_SELECTORS = {
    "name": ["input[name*='name']", "input[id*='name']"],
    "email": ["input[name*='email']", "input[id*='email']"],
    "phone": ["input[name*='phone']", "input[id*='phone']"],
}

RESUME_SELECTORS = [
    "input[type='file'][name*='resume']",
    "input[type='file']",
]

CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
    "#captcha",
    ".g-recaptcha",
    "[data-sitekey]",
]


class IndeedApplier:
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

            logger.info("Indeed: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(2, 4)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            apply_btn = await self._find_element(page, APPLY_BUTTON_SELECTORS, timeout=8000)
            if not apply_btn:
                current_url = page.url
                if "indeed.com" not in current_url:
                    result["error"] = "Redirected to external ATS"
                else:
                    result["error"] = "Apply button not found"
                result["status"] = "skipped"
                return result

            if self.dry_run:
                logger.info("[DRY_RUN] Would apply to %s at %s via Indeed", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            await apply_btn.click()
            await human_delay(2, 3)

            current_url = page.url
            if "indeed.com" not in current_url:
                result["error"] = "Redirected to external ATS"
                result["status"] = "skipped"
                return result

            max_steps = 8
            for step in range(max_steps):
                if await self._detect_captcha(page):
                    return {"status": "captcha", "error": "CAPTCHA detected in application form"}

                await self._fill_form_fields(page)

                resume_path = self.profile.get("resume_path", "")
                if resume_path and Path(resume_path).exists():
                    for selector in RESUME_SELECTORS:
                        fi = await page.query_selector(selector)
                        if fi:
                            try:
                                await fi.set_input_files(resume_path)
                                await human_delay(1, 2)
                                break
                            except Exception:
                                pass

                if await self._safe_click_first(page, SUBMIT_SELECTORS, timeout=2000):
                    await human_delay(2, 4)
                    result["status"] = "applied"
                    logger.info("Applied to %s at %s via Indeed", job.get("title"), job.get("company"))
                    return result

                if not await self._safe_click_first(page, CONTINUE_SELECTORS, timeout=2000):
                    break
                await human_delay(1, 2)

            result["error"] = "Could not complete Indeed application"
            result["status"] = "failed"

        except Exception as e:
            result["error"] = str(e)
            logger.error("Indeed apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _fill_form_fields(self, page):
        personal = self.profile.get("personal", {})
        field_values = {
            "name": personal.get("full_name", ""),
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
        }
        for key, value in field_values.items():
            if value:
                await self._safe_fill(page, FIELD_SELECTORS[key], value)

    async def _safe_fill(self, page, selectors: list, value: str) -> bool:
        if not value:
            return False
        el = await self._find_element(page, selectors)
        if not el:
            return False
        try:
            current = await el.input_value()
            if not current:
                await el.fill("")
                await el.fill(value)
                await human_delay(0.3, 0.6)
            return True
        except Exception:
            return False

    async def _safe_click_first(self, page, selectors: list, timeout: int = 3000) -> bool:
        el = await self._find_element(page, selectors, timeout=timeout)
        if el:
            try:
                is_visible = await el.is_visible()
                if is_visible:
                    await el.click()
                    return True
            except Exception:
                pass
        return False

    async def _find_element(self, page, selectors: list, timeout: int = 5000):
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
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
