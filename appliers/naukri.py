from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("applier.naukri")


class NaukriApplier:
    ELEMENT_TIMEOUT = 10000
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

            logger.info("Naukri: applying to %s at %s", job.get("title"), job.get("company"))
            await page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            await human_delay(3, 5)

            already_applied = await page.query_selector("#already-applied")
            if already_applied:
                result["status"] = "skipped"
                result["error"] = "Already applied"
                return result

            alert_el = await page.query_selector("[class*='styles_alert-message-text']")
            if alert_el:
                try:
                    text = await alert_el.inner_text()
                    if "expired" in text.lower():
                        result["status"] = "skipped"
                        result["error"] = "Job expired"
                        return result
                except Exception:
                    pass

            company_site = await page.query_selector("#company-site-button")
            if company_site:
                result["status"] = "skipped"
                result["error"] = "Redirects to company site"
                return result

            jd_container = await page.query_selector(".jdContainer")
            if jd_container:
                result["status"] = "skipped"
                result["error"] = "External JD container"
                return result

            if self.dry_run:
                logger.info("[DRY_RUN] Would apply to %s at %s via Naukri", job.get("title"), job.get("company"))
                result["status"] = "dry_run"
                return result

            apply_btn = await page.query_selector("//*[text()='Apply']")
            if not apply_btn:
                apply_btn = await page.query_selector("button:has-text('Apply'), input[value='Apply']")

            if not apply_btn:
                result["error"] = "No Apply button found"
                result["status"] = "skipped"
                return result

            await apply_btn.click()
            await human_delay(3, 5)

            await self._handle_questions(page)

            success = await page.query_selector("//span[contains(@class, 'apply-message') and contains(text(), 'successfully applied')]")
            if success:
                result["status"] = "applied"
                logger.info("Applied to %s at %s via Naukri", job.get("title"), job.get("company"))
            else:
                apply_status = await page.query_selector("//div[contains(@class, 'apply-status-header') and contains(@class, 'green')]")
                if apply_status:
                    result["status"] = "applied"
                    logger.info("Applied to %s at %s via Naukri", job.get("title"), job.get("company"))
                else:
                    result["error"] = "Application submission confirmation not found"
                    result["status"] = "failed"

        except Exception as e:
            result["error"] = str(e)
            logger.error("Naukri apply error: %s", e)
        finally:
            await page.close()
        return result

    async def _handle_questions(self, page):
        max_questions = 15
        for q in range(max_questions):
            try:
                radio_btns = await page.query_selector_all(".ssrc__radio-btn-container")
                if radio_btns:
                    question_el = await page.query_selector("//li[contains(@class, 'botItem')]/div/div/span")
                    if question_el:
                        await radio_btns[0].click()
                        await human_delay(1, 2)
                        save_btn = await page.query_selector("//*[text()='Save']")
                        if save_btn:
                            await save_btn.click()
                            await human_delay(1, 2)
                            continue

                chat_list = await page.query_selector("//ul[contains(@id, 'chatList_')]")
                if chat_list:
                    li_elements = await chat_list.query_selector_all("li")
                    if li_elements:
                        last_text = await li_elements[-1].inner_text()
                        input_field = await page.query_selector("//div[@class='textArea']")
                        if input_field:
                            if self.answer_engine:
                                answer = self.answer_engine.answer_screening(last_text, self.profile)
                                await input_field.fill(answer)
                            else:
                                await input_field.fill("Yes")
                            await human_delay(1, 2)
                            save_btn = await page.query_selector("//*[text()='Save']")
                            if save_btn:
                                await save_btn.click()
                                await human_delay(1, 2)
                                continue

                success = await page.query_selector(
                    "//span[contains(@class, 'apply-message') and contains(text(), 'successfully applied')]")
                if success:
                    break

            except Exception as e:
                logger.debug("Naukri question handling: %s", e)
                break
