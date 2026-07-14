from pathlib import Path
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("applier.indeed")


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

            apply_btn = await self._wait_and_query(page,
                "button#indeedApplyButton, button[id*='indeedApply'], "
                ".jobsearch-IndeedApplyButton-newDesign, button[aria-label*='Apply now']",
                timeout=8000)
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
                    for selector in ["input[type='file'][name*='resume']", "input[type='file']"]:
                        fi = await page.query_selector(selector)
                        if fi:
                            try:
                                await fi.set_input_files(resume_path)
                                await human_delay(1, 2)
                                break
                            except Exception:
                                pass

                if await self._safe_click(page,
                    "button[aria-label*='Submit'], button.ia-continueButton[type='submit'], button[id*='submit']",
                    timeout=2000):
                    await human_delay(2, 4)
                    result["status"] = "applied"
                    logger.info("Applied to %s at %s via Indeed", job.get("title"), job.get("company"))
                    return result

                if not await self._safe_click(page,
                    "button.ia-continueButton, button[aria-label*='Continue'], button[id*='continue']",
                    timeout=2000):
                    break
                await human_delay(1, 2)

            result["error"] = "Could not complete Indeed application — ran out of steps"
            result["status"] = "failed"

        except Exception as e:
            result["error"] = str(e)
            logger.error("Indeed apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _fill_form_fields(self, page):
        personal = self.profile.get("personal", {})
        fields = {
            "input[name*='name'], input[id*='name']": personal.get("full_name", ""),
            "input[name*='email'], input[id*='email']": personal.get("email", ""),
            "input[name*='phone'], input[id*='phone']": personal.get("phone", ""),
        }
        for selector, value in fields.items():
            if value:
                el = await page.query_selector(selector)
                if el:
                    try:
                        current = await el.input_value()
                        if not current:
                            await el.fill("")
                            await el.fill(value)
                            await human_delay(0.3, 0.6)
                    except Exception:
                        pass

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
