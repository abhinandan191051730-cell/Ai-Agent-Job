import time
from urllib.parse import quote_plus
from typing import Optional
from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("scraper.linkedin")

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs/search/"


class LinkedInScraper:
    def __init__(self, browser: BrowserManager):
        self.browser = browser

    async def search(self, keywords: str = None, location: str = None, max_results: int = 100):
        ctx = await self.browser.get_context()
        page = await ctx.new_page()
        jobs = []
        try:
            title = keywords or self._get_default_title()
            loc = location or "India"

            logger.info("LinkedIn: searching '%s' in '%s'", title, loc)
            url = f"{LINKEDIN_SEARCH_URL}?keywords={quote_plus(title)}&location={quote_plus(loc)}&f_TPR=r604800"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3, 5)

            if "login" in page.url or "authwall" in page.url:
                logger.warning("LinkedIn requires login. Please log in via the browser first.")
                return jobs

            found = 0
            page_num = 0
            while found < max_results:
                job_cards = await page.query_selector_all(
                    ".jobs-search-results__list-item, .job-card-container, [data-occludable-job-id]"
                )
                if not job_cards:
                    logger.info("LinkedIn: no job cards found on page %d", page_num)
                    break

                for card in job_cards:
                    if found >= max_results:
                        break
                    try:
                        job = await self._extract_job(page, card)
                        if job:
                            jobs.append(job)
                            found += 1
                    except Exception as e:
                        logger.debug("LinkedIn: failed to extract job card: %s", e)

                page_num += 1
                next_btn = await page.query_selector(
                    "button[aria-label='Next'], .artdeco-pagination__button--next"
                )
                if not next_btn:
                    break
                try:
                    is_disabled = await next_btn.is_disabled()
                    if is_disabled:
                        break
                    await next_btn.click()
                    await human_delay(2, 4)
                except Exception:
                    break

        except Exception as e:
            logger.error("LinkedIn search error: %s", e)
        finally:
            await page.close()

        logger.info("Found %d jobs on LinkedIn", len(jobs))
        return jobs

    async def _extract_job(self, page, card) -> Optional[dict]:
        try:
            await card.click()
            await human_delay(1, 2)
        except Exception as e:
            logger.debug("LinkedIn: failed to click job card: %s", e)
            return None

        title_el = await page.query_selector(
            ".job-details-jobs-unified-top-card__job-title, "
            ".jobs-unified-top-card__job-title, h2.t-24"
        )
        company_el = await page.query_selector(
            ".job-details-jobs-unified-top-card__company-name, "
            ".jobs-unified-top-card__company-name, a.ember-view.t-black.t-normal"
        )
        location_el = await page.query_selector(
            ".job-details-jobs-unified-top-card__primary-description-container .tvm__text, "
            ".jobs-unified-top-card__bullet"
        )
        desc_el = await page.query_selector(
            ".jobs-description__content, .jobs-box__html-content, #job-details"
        )

        title = await title_el.inner_text() if title_el else None
        company = await company_el.inner_text() if company_el else None
        location_text = await location_el.inner_text() if location_el else ""
        description = await desc_el.inner_text() if desc_el else ""

        if not title or not company:
            return None

        title = title.strip()
        company = company.strip()
        location_text = location_text.strip()

        job_id = await card.get_attribute("data-occludable-job-id") or ""
        if not job_id:
            current_url = page.url
            if "currentJobId=" in current_url:
                job_id = current_url.split("currentJobId=")[1].split("&")[0]

        if not job_id:
            return None

        salary_el = await page.query_selector(
            ".job-details-jobs-unified-top-card__job-insight--highlight, "
            ".salary-main-rail__compensation-value"
        )
        salary = await salary_el.inner_text() if salary_el else None

        apply_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

        return {
            "title": title,
            "company": company,
            "location": location_text,
            "salary": salary.strip() if salary else None,
            "description": description.strip() if description else "",
            "url": apply_url,
            "platform": "linkedin",
            "external_id": f"linkedin-{job_id}",
            "posting_date": None,
            "source": "linkedin",
        }

    def _get_default_title(self) -> str:
        target_roles = ["SOC Analyst", "Security Analyst", "VAPT Analyst", "Penetration Tester"]
        return target_roles[0]
