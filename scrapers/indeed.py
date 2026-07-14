from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("scraper.indeed")


class IndeedScraper:
    def __init__(self, browser: BrowserManager):
        self.browser = browser

    async def search(self, keywords: str = None, location: str = None, max_pages: int = 3):
        ctx = await self.browser.get_context()
        page = await ctx.new_page()
        jobs = []
        base_url = "https://in.indeed.com/jobs?"
        params = []
        if keywords:
            params.append(f"q={keywords.replace(' ', '+')}")
        if location:
            params.append(f"l={location.replace(' ', '+')}")
        search_url = base_url + "&".join(params)
        logger.info("Searching Indeed: %s", search_url)
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3, 6)
            for p in range(max_pages):
                await human_delay(2, 4)
                cards = await page.query_selector_all(".job_seen_beacon, .result, .cardOutline, td.resultContent")
                if not cards:
                    cards = await page.query_selector_all("[data-jk]")
                for card in cards:
                    try:
                        title_el = await card.query_selector("h2.jobTitle a, .jobTitle a, a[data-jk]")
                        company_el = await card.query_selector("[data-testid='text-location'], .companyName, .company_location")
                        loc_el = await card.query_selector("[data-testid='text-location'], .companyLocation")
                        title = await title_el.get_attribute("title") or await title_el.inner_text() if title_el else ""
                        url = await title_el.get_attribute("href") if title_el else ""
                        company = await company_el.inner_text() if company_el else ""
                        loc = await loc_el.inner_text() if loc_el else ""
                        jobs.append({
                            "title": title.strip(),
                            "company": company.strip(),
                            "location": loc.strip(),
                            "url": url.strip() if url.startswith("http") else f"https://in.indeed.com{url}",
                            "source": "indeed",
                            "platform": "indeed",
                        })
                    except Exception as e:
                        logger.debug("Skipping card: %s", e)
                try:
                    next_btn = await page.query_selector("a[aria-label='Next'], a[data-testid='pagination-page-next']")
                    if next_btn:
                        await next_btn.click()
                        await human_delay(2, 4)
                    else:
                        break
                except Exception:
                    break
        except Exception as e:
            logger.error("Indeed search error: %s", e)
        finally:
            await page.close()
        logger.info("Found %d jobs on Indeed", len(jobs))
        return jobs
