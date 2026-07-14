from pathlib import Path
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("applier.ashby")


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

            await self._safe_click(page,
                'a:has-text("Apply for this job"), button:has-text("Apply for this job"), '
                'a:has-text("Apply"), button:has-text("Apply")',
                timeout=3000)

            if self.dry_run:
                logger.info("[DRY_RUN] Would fill Ashby application for %s at %s", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            await self._fill_form_fields(page)

            resume_path = self.profile.get("resume_path", "")
            if resume_path and Path(resume_path).exists():
                for selector in [
                    'input[type="file"][name*="resume"]',
                    'input[type="file"][accept*="pdf"]',
                    'input[type="file"]',
                ]:
                    fi = await page.query_selector(selector)
                    if fi:
                        try:
                            await fi.set_input_files(resume_path)
                            await human_delay(1, 2)
                            break
                        except Exception:
                            pass

            await self._fill_cover_letter(page)
            await human_delay(1, 2)

            submit_btn = await self._wait_and_query(page,
                'button[type="submit"]:has-text("Submit"), button[type="submit"]:has-text("Apply"), button[type="submit"]',
                timeout=5000)
            if not submit_btn:
                result["error"] = "Submit button not found on Ashby form"
                result["status"] = "failed"
                return result

            await submit_btn.click()
            await human_delay(2, 4)

            success_el = await self._wait_and_query(page,
                'text="Your application has been submitted", text="Application submitted", '
                'text="Thank you", h1:has-text("Thank"), h2:has-text("Thank")',
                timeout=5000)
            if success_el:
                result["status"] = "applied"
                logger.info("Applied to %s at %s via Ashby", job.get("title"), job.get("company"))
                return result

            error_el = await page.query_selector('[role="alert"], .error-message, .form-error')
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

        fields = [
            ('input[name="name"], input[name*="Name"]:not([name*="last"])', full_name),
            ('input[name*="firstName"], input[name*="first_name"]', first),
            ('input[name*="lastName"], input[name*="last_name"]', last),
            ('input[name="email"], input[name*="email"], input[type="email"]', personal.get("email", "")),
            ('input[name="phone"], input[name*="phone"], input[type="tel"]', personal.get("phone", "")),
        ]
        for selector, value in fields:
            if value:
                el = await page.query_selector(selector)
                if el:
                    try:
                        await el.fill("")
                        await el.fill(value)
                        await human_delay(0.3, 0.6)
                    except Exception:
                        pass

        linkedin = personal.get("linkedin", "")
        if linkedin:
            await self._safe_fill(page,
                'input[name*="linkedin"], input[name*="LinkedIn"], input[placeholder*="LinkedIn"]',
                linkedin)

    async def _fill_cover_letter(self, page):
        textarea = await page.query_selector(
            'textarea[name*="cover"], textarea[name*="Cover"], textarea[name*="letter"], '
            'textarea[placeholder*="cover letter"]'
        )
        if textarea:
            try:
                is_visible = await textarea.is_visible()
                current = await textarea.input_value()
                if is_visible and not current:
                    await textarea.fill("I am excited to apply for this position. My background and skills align well with the requirements of this role.")
                    await human_delay(0.5, 1)
                    return
            except Exception:
                pass

        additional = await page.query_selector(
            'textarea[name*="additional"], textarea[placeholder*="additional"], textarea[placeholder*="anything else"]'
        )
        if additional:
            try:
                is_visible = await additional.is_visible()
                current = await additional.input_value()
                if is_visible and not current:
                    await additional.fill("I have relevant experience that makes me a strong candidate for this role.")
                    await human_delay(0.5, 1)
            except Exception:
                pass

    async def _safe_fill(self, page, selector: str, value: str) -> bool:
        if not value:
            return False
        el = await page.query_selector(selector)
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

    async def _safe_click(self, page, selector: str, timeout: int = 3000) -> bool:
        el = await self._wait_and_query(page, selector, timeout=timeout)
        if el:
            try:
                is_visible = await el.is_visible()
                if is_visible:
                    await el.click()
                    return True
            except Exception:
                pass
        return False

    async def _wait_and_query(self, page, selector: str, timeout: int = 5000):
        try:
            await page.wait_for_selector(selector, timeout=timeout, state="visible")
            return await page.query_selector(selector)
        except Exception:
            return None

    async def _detect_captcha(self, page) -> bool:
        for selector in ["iframe[src*='captcha']", "iframe[src*='recaptcha']", "#captcha", ".g-recaptcha", "[data-sitekey]"]:
            el = await page.query_selector(selector)
            if el:
                return True
        return False
