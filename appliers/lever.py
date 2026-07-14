from pathlib import Path
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("applier.lever")


class LeverApplier:
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

            if "/apply" not in url:
                url = url.rstrip("/") + "/apply"

            logger.info("Lever: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(2, 4)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            form = await self._wait_and_query(page,
                "form.application-form, form[action*='apply'], .application-form, form.postings-form",
                timeout=8000)
            if not form:
                result["error"] = "Lever application form not found"
                result["status"] = "skipped"
                return result

            if self.dry_run:
                logger.info("[DRY_RUN] Would fill Lever application for %s at %s", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            await self._fill_form_fields(page)

            resume_path = self.profile.get("resume_path", "")
            if resume_path and Path(resume_path).exists():
                for selector in [
                    "input[type='file'][name='resume']",
                    "input[type='file'][name*='resume']",
                    "input[type='file']",
                ]:
                    file_input = await page.query_selector(selector)
                    if file_input:
                        try:
                            await file_input.set_input_files(resume_path)
                            await human_delay(1, 2)
                            break
                        except Exception:
                            pass

            await self._fill_cover_letter(page, job)
            await human_delay(1, 2)

            submit_btn = await self._wait_and_query(page,
                "button.postings-btn[type='submit'], button[type='submit'], "
                "button.postings-btn-submit, input[type='submit']",
                timeout=5000)
            if not submit_btn:
                result["error"] = "Submit button not found on Lever form"
                result["status"] = "failed"
                return result

            await submit_btn.click()
            await human_delay(2, 4)

            error_el = await self._wait_and_query(page, ".application-error, .error-message, .form-error", timeout=3000)
            if error_el:
                try:
                    error_text = await error_el.inner_text()
                    result["error"] = f"Lever form error: {error_text[:200]}"
                    result["status"] = "failed"
                    return result
                except Exception:
                    pass

            result["status"] = "applied"
            logger.info("Applied to %s at %s via Lever", job.get("title"), job.get("company"))

        except Exception as e:
            result["error"] = str(e)
            logger.error("Lever apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _fill_form_fields(self, page):
        personal = self.profile.get("personal", {})
        fields = {
            "input[name='name']": personal.get("full_name", ""),
            "input[name='email']": personal.get("email", ""),
            "input[name='phone']": personal.get("phone", ""),
        }
        for selector, value in fields.items():
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
                "input[name='urls[LinkedIn]'], input[name*='linkedin'], input[placeholder*='LinkedIn']",
                linkedin)

    async def _fill_cover_letter(self, page, job):
        cover_text = ""
        if self.answer_engine:
            cover_text = self.answer_engine.generate_cover_letter(job, self.profile)
        if not cover_text:
            return
        textarea = await page.query_selector(
            "textarea[name='comments'], textarea[name*='cover'], textarea.application-answer-alternative"
        )
        if textarea:
            try:
                current = await textarea.input_value()
                if not current:
                    await textarea.fill(cover_text)
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
