from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger
from utils.exceptions import SelectorNotFoundError

logger = get_logger("applier.linkedin")

EASY_APPLY_SELECTORS = [
    "button.jobs-apply-button",
    "button[aria-label*='Easy Apply']",
    ".jobs-apply-button--top-card",
    "button[data-control-name='jobdetails_topcard_inapply']",
    "button:has-text('Easy Apply')",
]

SUBMIT_SELECTORS = [
    "button[aria-label*='Submit application']",
    "button[aria-label*='Submit']",
    "button[type='submit']",
]

CONTINUE_SELECTORS = [
    "button[aria-label*='Continue']",
    "button[aria-label*='Next']",
    "button[aria-label*='Review']",
]

DISMISS_SELECTORS = [
    "button[aria-label*='Dismiss']",
    "[data-test-modal-close-btn]",
    "button[aria-label*='Close']",
]

PHONE_SELECTORS = [
    "input[name*='phone']",
    "input[id*='phone']",
    "input[aria-label*='phone']",
]

RESUME_SELECTORS = [
    "input[type='file'][name*='resume']",
    "input[type='file']",
]

COVER_LETTER_SELECTORS = [
    "textarea[name*='cover']",
    "textarea[id*='cover']",
    "textarea[aria-label*='cover']",
    "textarea[data-test-form-builder-radio-button-form-component-*]",
]

CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
    "#captcha",
    ".g-recaptcha",
    "[data-sitekey]",
]


class LinkedInApplier:
    ELEMENT_TIMEOUT = 5000
    NAV_TIMEOUT = 30000

    def __init__(self, browser: BrowserManager, profile: dict, answer_engine=None, dry_run: bool = False):
        self.browser = browser
        self.profile = profile
        self.answer_engine = answer_engine
        self.dry_run = dry_run

    async def apply(self, job: dict) -> dict:
        ctx = await self.browser.get_context()
        page = await ctx.new_page()
        result = {"status": "failed", "error": None}
        try:
            url = job.get("url", "")
            if not url:
                raise ValueError("No URL provided")

            logger.info("LinkedIn: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(3, 5)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            easy_apply_btn = await self._find_element(page, EASY_APPLY_SELECTORS, timeout=8000)
            if not easy_apply_btn:
                result["error"] = "Easy Apply button not found — external application required"
                result["status"] = "skipped"
                return result

            if self.dry_run:
                logger.info("[DRY_RUN] Would click Easy Apply for %s at %s", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            await easy_apply_btn.click()
            await human_delay(2, 3)

            max_steps = 10
            for step in range(max_steps):
                if await self._detect_captcha(page):
                    return {"status": "captcha", "error": "CAPTCHA detected in application form"}

                await self._fill_phone(page)

                resume_path = self.profile.get("resume_path", "")
                if resume_path:
                    fi = await self._find_element(page, RESUME_SELECTORS)
                    if fi:
                        try:
                            await fi.set_input_files(resume_path)
                            await human_delay(1, 2)
                        except Exception:
                            pass

                await self._fill_cover_letter(page, job)

                if await self._safe_click_first(page, SUBMIT_SELECTORS, timeout=2000):
                    await human_delay(2, 4)
                    await self._safe_click_first(page, DISMISS_SELECTORS, timeout=3000)
                    result["status"] = "applied"
                    logger.info("Applied to %s at %s via LinkedIn", job.get("title"), job.get("company"))
                    return result

                if not await self._safe_click_first(page, CONTINUE_SELECTORS, timeout=2000):
                    break
                await human_delay(1, 2)

            result["error"] = "Could not complete Easy Apply — ran out of steps"
            result["status"] = "failed"

        except Exception as e:
            result["error"] = str(e)
            logger.error("LinkedIn apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _fill_phone(self, page):
        phone = self.profile.get("personal", {}).get("phone", "")
        if not phone:
            return
        el = await self._find_element(page, PHONE_SELECTORS)
        if el:
            try:
                current = await el.input_value()
                if not current:
                    await el.fill("")
                    await el.fill(phone)
                    await human_delay(0.5, 1)
            except Exception:
                pass

    async def _fill_cover_letter(self, page, job):
        textarea = await self._find_element(page, COVER_LETTER_SELECTORS)
        if not textarea:
            return
        try:
            is_visible = await textarea.is_visible()
            current = await textarea.input_value()
            if is_visible and not current:
                cover_text = ""
                if self.answer_engine:
                    cover_text = self.answer_engine.generate_cover_letter(job, self.profile)
                if not cover_text:
                    cover_text = "I am excited to apply for this position. My background and skills align well with the requirements of this role."
                await textarea.fill(cover_text)
                await human_delay(0.5, 1)
        except Exception:
            pass

    async def _find_element(self, page, selectors: list, timeout: int = 5000):
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
                if el:
                    return el
            except Exception:
                continue
        return None

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

    async def _detect_captcha(self, page) -> bool:
        for selector in CAPTCHA_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                return True
        return False
