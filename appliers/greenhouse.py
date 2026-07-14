from pathlib import Path
from typing import Optional
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger
from utils.exceptions import SelectorNotFoundError

logger = get_logger("applier.greenhouse")

APPLY_BUTTON_SELECTORS = [
    "a#apply_button",
    "a[href*='#app']",
    "button[id*='apply']",
    "a.btn[href*='apply']",
    "a:has-text('Apply')",
]

SUBMIT_SELECTORS = [
    "input[type='submit']#submit_app",
    "input[type='submit'][value*='Submit']",
    "button[type='submit']",
    "input#submit_app",
]

RESUME_SELECTORS = [
    "input[type='file'][name*='resume']",
    "input[type='file'][id*='resume']",
    "input[type='file'][data-field*='resume']",
    "input[type='file']",
]

COVER_LETTER_SELECTORS = [
    "textarea[name*='cover_letter']",
    "textarea[id*='cover_letter']",
    "textarea[name*='cover']",
    "#cover_letter",
]

FIELD_SELECTORS = {
    "first_name": ["#first_name", "input[name*='first_name']", "input[name*='firstName']"],
    "last_name": ["#last_name", "input[name*='last_name']", "input[name*='lastName']"],
    "email": ["#email", "input[name*='email']", "input[type='email']"],
    "phone": ["#phone", "input[name*='phone']", "input[type='tel']"],
    "linkedin": ["input[name*='linkedin']", "input[id*='linkedin']", "input[autocomplete*='url']"],
}

ERROR_SELECTORS = [".field_with_errors", ".error", "#application_errors"]

CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
    "#captcha",
    ".g-recaptcha",
    "[data-sitekey]",
]


class GreenhouseApplier:
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

            logger.info("Greenhouse: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(2, 4)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            if not await self._safe_click_first(page, APPLY_BUTTON_SELECTORS, timeout=3000):
                raise SelectorNotFoundError("Apply button", APPLY_BUTTON_SELECTORS, page.url)

            if self.dry_run:
                logger.info("[DRY_RUN] Would fill Greenhouse application for %s at %s", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            await self._fill_form_fields(page)
            await self._upload_resume(page)
            await self._fill_cover_letter(page, job)

            await human_delay(1, 2)
            submit_btn = await self._find_element(page, SUBMIT_SELECTORS, timeout=5000)
            if not submit_btn:
                raise SelectorNotFoundError("Submit button", SUBMIT_SELECTORS, page.url)

            await submit_btn.click()
            await human_delay(2, 4)

            error_el = await self._find_element(page, ERROR_SELECTORS, timeout=3000)
            if error_el:
                try:
                    error_text = await error_el.inner_text()
                    result["error"] = f"Greenhouse form error: {error_text[:200]}"
                    result["status"] = "failed"
                    return result
                except Exception:
                    pass

            result["status"] = "applied"
            logger.info("Applied to %s at %s via Greenhouse", job.get("title"), job.get("company"))

        except SelectorNotFoundError:
            raise
        except Exception as e:
            result["error"] = str(e)
            logger.error("Greenhouse apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _fill_form_fields(self, page):
        personal = self.profile.get("personal", {})
        full_name = personal.get("full_name", "") or ""
        names = full_name.split()
        first_name = names[0] if names else ""
        last_name = " ".join(names[1:]) if len(names) > 1 else ""

        field_values = {
            "first_name": first_name,
            "last_name": last_name,
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
        }
        for key, value in field_values.items():
            await self._safe_fill(page, FIELD_SELECTORS[key], value)

        linkedin = personal.get("linkedin", "")
        if linkedin:
            await self._safe_fill(page, FIELD_SELECTORS["linkedin"], linkedin)

    async def _upload_resume(self, page):
        resume_path = self.profile.get("resume_path", "")
        if not resume_path or not Path(resume_path).exists():
            return
        for selector in RESUME_SELECTORS:
            file_input = await page.query_selector(selector)
            if file_input:
                try:
                    await file_input.set_input_files(resume_path)
                    await human_delay(1, 2)
                    return
                except Exception as e:
                    logger.debug("Upload failed via %s: %s", selector, e)

    async def _fill_cover_letter(self, page, job):
        cover_text = ""
        if self.answer_engine:
            cover_text = self.answer_engine.generate_cover_letter(job, self.profile)
        if not cover_text:
            return
        textarea = await self._find_element(page, COVER_LETTER_SELECTORS)
        if textarea:
            try:
                current = await textarea.input_value()
                if not current:
                    await textarea.fill(cover_text)
                    await human_delay(0.5, 1)
            except Exception:
                pass

    async def _safe_fill(self, page, selectors: list, value: str) -> bool:
        if not value:
            return False
        el = await self._find_element(page, selectors)
        if not el:
            return False
        try:
            is_visible = await el.is_visible()
            if not is_visible:
                return False
            current = await el.input_value()
            if current == value:
                return False
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
