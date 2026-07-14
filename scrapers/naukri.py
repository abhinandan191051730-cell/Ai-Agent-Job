from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("scraper.naukri")


class NaukriScraper:
    def __init__(self, browser: BrowserManager):
        self.browser = browser

    async def search(self, keywords: str = None, location: str = None, max_pages: int = 3):
        ctx = await self.browser.get_context()
        page = await ctx.new_page()
        jobs = []
        search_url = "https://www.naukri.com/"
        if keywords:
            search_url += f"{keywords.replace(' ', '-')}-jobs"
        if location:
            search_url += f"-in-{location.replace(' ', '-')}"
        search_url += "?k=" + (keywords or "").replace(" ", "+")
        logger.info("Searching Naukri: %s", search_url)
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3, 6)
            for p in range(max_pages):
                await human_delay(2, 4)
                cards = await page.query_selector_all(".jobTuple, .cust-job-tuple, article.jobTuple")
                if not cards:
                    cards = await page.query_selector_all("div[class*='job']")
                for card in cards:
                    try:
                        title_el = await card.query_selector("a.title, .title, [class*='title']")
                        company_el = await card.query_selector("a.subTitle, .subTitle, [class*='company']")
                        loc_el = await card.query_selector("li.location, span.location, [class*='location']")
                        url_el = await card.query_selector("a.title")
                        title = await title_el.get_attribute("title") or await title_el.inner_text() if title_el else ""
                        company = await company_el.inner_text() if company_el else ""
                        loc = await loc_el.inner_text() if loc_el else ""
                        url = await url_el.get_attribute("href") if url_el else ""
                        jobs.append({
                            "title": title.strip(),
                            "company": company.strip(),
                            "location": loc.strip(),
                            "url": url.strip(),
                            "source": "naukri",
                            "platform": "naukri",
                        })
                    except Exception as e:
                        logger.debug("Skipping card: %s", e)
                try:
                    next_btn = await page.query_selector("a[title='Next']")
                    if next_btn:
                        await next_btn.click()
                        await human_delay(2, 4)
                    else:
                        break
                except Exception:
                    break
        except Exception as e:
            logger.error("Naukri search error: %s", e)
        finally:
            await page.close()
        logger.info("Found %d jobs on Naukri", len(jobs))
        return jobs
