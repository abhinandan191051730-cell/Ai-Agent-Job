from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("applier.linkedin")


class LinkedInApplier:
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

            logger.info("LinkedIn: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(3, 5)

            if await self._detect_captcha(page):
                return {"status": "captcha", "error": "CAPTCHA detected"}

            easy_apply_btn = await self._wait_and_query(page,
                "button.jobs-apply-button, button[aria-label*='Easy Apply'], "
                ".jobs-apply-button--top-card",
                timeout=8000)
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
                    for selector in ["input[type='file'][name*='resume']", "input[type='file']"]:
                        fi = await page.query_selector(selector)
                        if fi:
                            try:
                                await fi.set_input_files(resume_path)
                                await human_delay(1, 2)
                                break
                            except Exception:
                                pass

                await self._fill_cover_letter(page)

                if await self._safe_click(page,
                    "button[aria-label*='Submit application'], button[aria-label*='Submit']",
                    timeout=2000):
                    await human_delay(2, 4)
                    await self._safe_click(page,
                        "button[aria-label*='Dismiss'], [data-test-modal-close-btn]",
                        timeout=3000)
                    result["status"] = "applied"
                    logger.info("Applied to %s at %s via LinkedIn", job.get("title"), job.get("company"))
                    return result

                if not await self._safe_click(page,
                    "button[aria-label*='Continue'], button[aria-label*='Next'], button[aria-label*='Review']",
                    timeout=2000):
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
        for selector in ["input[name*='phone'], input[id*='phone']"]:
            el = await page.query_selector(selector)
            if el:
                try:
                    current = await el.input_value()
                    if not current:
                        await el.fill("")
                        await el.fill(phone)
                        await human_delay(0.5, 1)
                    return
                except Exception:
                    pass

    async def _fill_cover_letter(self, page):
        textarea = await page.query_selector(
            "textarea[name*='cover'], textarea[id*='cover'], textarea[aria-label*='cover']"
        )
        if textarea:
            try:
                is_visible = await textarea.is_visible()
                current = await textarea.input_value()
                if is_visible and not current:
                    await textarea.fill("I am excited to apply for this position. My background in cybersecurity aligns well with the role.")
                    await human_delay(0.5, 1)
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
