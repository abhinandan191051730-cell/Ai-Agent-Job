from pathlib import Path
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger
from utils.exceptions import SelectorNotFoundError

logger = get_logger("applier.ashby")

APPLY_BUTTON_SELECTORS = [
    'a:has-text("Apply for this job")',
    'button:has-text("Apply for this job")',
    'a:has-text("Apply")',
    'button:has-text("Apply")',
]

FIELD_SELECTORS = {
    "name": ['input[name="name"]', 'input[name*="Name"]:not([name*="last"])', "input#name"],
    "first_name": ['input[name*="firstName"]', 'input[name*="first_name"]', "input#firstName"],
    "last_name": ['input[name*="lastName"]', 'input[name*="last_name"]', "input#lastName"],
    "email": ['input[name="email"]', 'input[name*="email"]', 'input[type="email"]'],
    "phone": ['input[name="phone"]', 'input[name*="phone"]', 'input[type="tel"]'],
    "linkedin": ['input[name*="linkedin"]', 'input[name*="LinkedIn"]', 'input[placeholder*="LinkedIn"]'],
}

RESUME_SELECTORS = [
    'input[type="file"][name*="resume"]',
    'input[type="file"][accept*="pdf"]',
    'input[type="file"]',
]

COVER_LETTER_SELECTORS = [
    'textarea[name*="cover"]',
    'textarea[name*="Cover"]',
    'textarea[name*="letter"]',
    'textarea[placeholder*="cover letter"]',
]

ADDITIONAL_TEXT_SELECTORS = [
    'textarea[name*="additional"]',
    'textarea[placeholder*="additional"]',
    'textarea[placeholder*="anything else"]',
]

SUBMIT_SELECTORS = [
    'button[type="submit"]:has-text("Submit")',
    'button[type="submit"]:has-text("Apply")',
    'button[type="submit"]',
]

SUCCESS_SELECTORS = [
    'text="Your application has been submitted"',
    'text="Application submitted"',
    'text="Thank you"',
    'h1:has-text("Thank")',
    'h2:has-text("Thank")',
]

ERROR_SELECTORS = [
    '[role="alert"]',
    '.error-message',
    '.form-error',
]

CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
    "#captcha",
    ".g-recaptcha",
    "[data-sitekey]",
]


class AshbyApplier:
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

            logger.info("Ashby: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(2, 4)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            if not await self._safe_click_first(page, APPLY_BUTTON_SELECTORS, timeout=3000):
                raise SelectorNotFoundError("Apply button", APPLY_BUTTON_SELECTORS, page.url)

            if self.dry_run:
                logger.info("[DRY_RUN] Would fill Ashby application for %s at %s", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

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

            await self._fill_cover_letter(page, job)
            await human_delay(1, 2)

            submit_btn = await self._find_element(page, SUBMIT_SELECTORS, timeout=5000)
            if not submit_btn:
                raise SelectorNotFoundError("Submit button", SUBMIT_SELECTORS, page.url)

            await submit_btn.click()
            await human_delay(2, 4)

            if await self._find_element(page, SUCCESS_SELECTORS, timeout=5000):
                result["status"] = "applied"
                logger.info("Applied to %s at %s via Ashby", job.get("title"), job.get("company"))
                return result

            error_el = await self._find_element(page, ERROR_SELECTORS, timeout=2000)
            if error_el:
                try:
                    is_visible = await error_el.is_visible()
                    if is_visible:
                        error_text = await error_el.inner_text()
                        result["error"] = f"Ashby form error: {error_text[:200]}"
                        result["status"] = "failed"
                        return result
                except Exception:
                    pass

            result["status"] = "applied"
            logger.info("Applied to %s at %s via Ashby (assumed success)", job.get("title"), job.get("company"))

        except SelectorNotFoundError:
            raise
        except Exception as e:
            result["error"] = str(e)
            logger.error("Ashby apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _fill_form_fields(self, page):
        personal = self.profile.get("personal", {})
        full_name = personal.get("full_name", "") or ""
        names = full_name.split()
        first = names[0] if names else ""
        last = " ".join(names[1:]) if len(names) > 1 else ""

        field_values = {
            "name": full_name,
            "first_name": first,
            "last_name": last,
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
        }
        for key, value in field_values.items():
            if value:
                await self._safe_fill(page, FIELD_SELECTORS[key], value)

        linkedin = personal.get("linkedin", "")
        if linkedin:
            await self._safe_fill(page, FIELD_SELECTORS["linkedin"], linkedin)

    async def _fill_cover_letter(self, page, job):
        textarea = await self._find_element(page, COVER_LETTER_SELECTORS)
        if textarea:
            try:
                is_visible = await textarea.is_visible()
                current = await textarea.input_value()
                if is_visible and not current:
                    cover_text = ""
                    if self.answer_engine:
                        cover_text = self.answer_engine.generate_cover_letter(job, self.profile)
                    if not cover_text:
                        cover_text = "I have relevant experience that makes me a strong candidate for this role."
                    await textarea.fill(cover_text)
                    await human_delay(0.5, 1)
                    return
            except Exception:
                pass

        additional = await self._find_element(page, ADDITIONAL_TEXT_SELECTORS)
        if additional:
            try:
                is_visible = await additional.is_visible()
                current = await additional.input_value()
                if is_visible and not current:
                    await additional.fill("I have relevant experience that makes me a strong candidate for this role.")
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
