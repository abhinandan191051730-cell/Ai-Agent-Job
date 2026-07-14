from pathlib import Path
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger
from utils.exceptions import SelectorNotFoundError

logger = get_logger("applier.workday")

APPLY_BUTTON_SELECTORS = [
    '[data-automation-id="adventureButton"]',
    '[data-automation-id="applyManually"]',
    'a[data-automation-id="jobPostingApplyButton"]',
    'button[data-automation-id="jobPostingApplyButton"]',
    'a:has-text("Apply"), button:has-text("Apply")',
]

AUTH_SELECTORS = {
    "create_account": ['[data-automation-id="createAccountLink"]'],
    "email": ['[data-automation-id="email"]', '[data-automation-id="signIn-email"]'],
    "signin_submit": ['[data-automation-id="signInSubmitButton"]', '[data-automation-id="createAccountSubmitButton"]'],
}

MY_INFO_SELECTORS = {
    "first_name": ['[data-automation-id="legalNameSection_firstName"]'],
    "last_name": ['[data-automation-id="legalNameSection_lastName"]'],
    "phone": ['[data-automation-id="phone-number"]'],
    "email": ['[data-automation-id="email"]'],
}

RESUME_SELECTORS = [
    '[data-automation-id="file-upload-input-ref"]',
    'input[type="file"][data-automation-id*="upload"]',
    'input[type="file"]',
]

NEXT_SELECTORS = [
    '[data-automation-id="bottom-navigation-next-button"]',
    'button:has-text("Next")',
]

SUBMIT_SELECTORS = [
    '[data-automation-id="bottom-navigation-next-button"]:has-text("Submit")',
    '[data-automation-id="submit-button"]',
    'button:has-text("Submit Application")',
    'button:has-text("Submit")',
]

SUCCESS_SELECTORS = [
    '[data-automation-id="thankYouMessage"]',
    'text="Thank you"',
    'text="Application submitted"',
    'text="Your application has been submitted"',
]

CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='recaptcha']",
    "#captcha",
    ".g-recaptcha",
    "[data-sitekey]",
]


class WorkdayApplier:
    ELEMENT_TIMEOUT = 8000
    NAV_TIMEOUT = 45000

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

            logger.info("Workday: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(3, 5)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            if not await self._click_apply_button(page):
                raise SelectorNotFoundError("Apply button", APPLY_BUTTON_SELECTORS, page.url)

            await human_delay(3, 5)

            if self.dry_run:
                logger.info("[DRY_RUN] Would fill Workday application for %s at %s", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            await self._handle_auth_page(page)

            max_steps = 12
            for step in range(max_steps):
                await human_delay(1, 2)

                if await self._detect_captcha(page):
                    return {"status": "captcha", "error": "CAPTCHA detected in application form"}

                if await self._is_submitted(page):
                    result["status"] = "applied"
                    logger.info("Applied to %s at %s via Workday", job.get("title"), job.get("company"))
                    return result

                await self._fill_my_information(page)
                await self._upload_resume(page)
                await self._fill_application_questions(page)
                await self._click_checkboxes(page)

                if not await self._click_next(page):
                    if await self._click_submit(page):
                        await human_delay(3, 5)
                        if await self._is_submitted(page):
                            result["status"] = "applied"
                            logger.info("Applied to %s at %s via Workday", job.get("title"), job.get("company"))
                            return result
                    break

                await human_delay(2, 3)

            if await self._is_submitted(page):
                result["status"] = "applied"
                logger.info("Applied to %s at %s via Workday", job.get("title"), job.get("company"))
                return result

            result["error"] = "Could not complete Workday application"
            result["status"] = "failed"

        except SelectorNotFoundError:
            raise
        except Exception as e:
            result["error"] = str(e)
            logger.error("Workday apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _click_apply_button(self, page) -> bool:
        return await self._safe_click_first(page, APPLY_BUTTON_SELECTORS, timeout=5000)

    async def _handle_auth_page(self, page):
        await human_delay(1, 2)
        personal = self.profile.get("personal", {})
        email = personal.get("email", "")

        if not await self._find_element(page, AUTH_SELECTORS["create_account"]) and \
           not await self._find_element(page, AUTH_SELECTORS["email"]):
            return

        email_input = await self._find_element(page, AUTH_SELECTORS["email"])
        if email_input:
            try:
                current = await email_input.input_value()
                if not current:
                    await email_input.fill("")
                    await email_input.fill(email)
                    await human_delay(0.5, 1)
            except Exception:
                pass

        await self._safe_click_first(page, AUTH_SELECTORS["signin_submit"], timeout=3000)

    async def _fill_my_information(self, page):
        personal = self.profile.get("personal", {})
        full_name = personal.get("full_name", "") or ""
        names = full_name.split()
        first = names[0] if names else ""
        last = " ".join(names[1:]) if len(names) > 1 else ""

        field_values = {
            "first_name": first,
            "last_name": last,
            "phone": personal.get("phone", ""),
            "email": personal.get("email", ""),
        }
        for key, value in field_values.items():
            if value:
                await self._safe_fill(page, MY_INFO_SELECTORS[key], value)

    async def _upload_resume(self, page):
        resume_path = self.profile.get("resume_path", "")
        if not resume_path or not Path(resume_path).exists():
            return
        for selector in RESUME_SELECTORS:
            fi = await page.query_selector(selector)
            if fi:
                try:
                    await fi.set_input_files(resume_path)
                    await human_delay(2, 3)
                    return
                except Exception as e:
                    logger.debug("Workday upload failed: %s", e)

    async def _fill_application_questions(self, page):
        textareas = await page.query_selector_all("textarea")
        for ta in textareas:
            try:
                is_visible = await ta.is_visible()
                current = await ta.input_value()
                if is_visible and not current:
                    await ta.fill("I am excited to apply for this position. My skills and experience match the requirements well.")
                    await human_delay(0.5, 1)
            except Exception:
                pass

    async def _click_checkboxes(self, page):
        checkboxes = await page.query_selector_all("input[type='checkbox']")
        for cb in checkboxes:
            try:
                is_checked = await cb.is_checked()
                if not is_checked:
                    await cb.check()
                    await human_delay(0.3, 0.6)
            except Exception:
                pass

    async def _click_next(self, page) -> bool:
        return await self._safe_click_first(page, NEXT_SELECTORS, timeout=3000)

    async def _click_submit(self, page) -> bool:
        return await self._safe_click_first(page, SUBMIT_SELECTORS, timeout=3000)

    async def _is_submitted(self, page) -> bool:
        return await self._find_element(page, SUCCESS_SELECTORS, timeout=2000) is not None

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
