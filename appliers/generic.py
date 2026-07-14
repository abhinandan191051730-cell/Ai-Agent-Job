from pathlib import Path
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("applier.generic")


class GenericApplier:
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
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3, 5)

            apply_btn = await page.query_selector("button:has-text('Apply'), a:has-text('Apply'), input[value='Apply']")
            if apply_btn:
                if self.dry_run:
                    logger.info("[DRY_RUN] Would fill application form for %s", url)
                    result["status"] = "dry_run"
                    return result
                await apply_btn.click()
                await human_delay(2, 4)

            personal = self.profile.get("personal", {})
            field_map = {
                "name": personal.get("full_name", ""),
                "full_name": personal.get("full_name", ""),
                "firstname": (personal.get("full_name", "") or "").split()[0] if personal.get("full_name") else "",
                "lastname": " ".join((personal.get("full_name", "") or "").split()[1:]),
                "email": personal.get("email", ""),
                "e_mail": personal.get("email", ""),
                "phone": personal.get("phone", ""),
                "telephone": personal.get("phone", ""),
                "mobile": personal.get("phone", ""),
                "linkedin": personal.get("linkedin", ""),
                "github": personal.get("github", ""),
                "portfolio": personal.get("portfolio", ""),
            }

            for field_name, value in field_map.items():
                if not value:
                    continue
                try:
                    for attr in ["name", "id", "aria-label", "placeholder", "data-testid"]:
                        sel = f"input[{attr}*='{field_name}']"
                        el = await page.query_selector(sel)
                        if el:
                            await el.fill("")
                            await el.fill(value)
                            await human_delay(0.3, 0.8)
                            break
                except Exception:
                    pass

            resume_path = self.profile.get("resume_path", "")
            if resume_path and Path(resume_path).exists():
                try:
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(resume_path)
                        await human_delay(1, 2)
                except Exception:
                    pass

            await human_delay(2, 4)
            submit_btn = await page.query_selector("button:has-text('Submit'), button[type='submit'], input[type='submit'], button:has-text('Send')")
            if submit_btn:
                await submit_btn.click()
                await human_delay(2, 3)
                result["status"] = "applied"
                logger.info("Applied to %s at %s via generic form", job.get("title"), job.get("company"))
            else:
                result["error"] = "No submit button found on generic form"
                result["status"] = "failed"
        except Exception as e:
            result["error"] = str(e)
            logger.error("Generic apply error: %s", e)
        finally:
            await page.close()
        return result
//fxgj