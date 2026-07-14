from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("scraper.instahyre")


class InstahyreScraper:
    def __init__(self, browser: BrowserManager):
        self.browser = browser

    async def search(self, keywords: str = None, location: str = None, max_pages: int = 3):
        ctx = await self.browser.get_context()
        page = await ctx.new_page()
        jobs = []
        search_url = "https://www.instahyre.com/search-jobs/"
        params = []
        if keywords:
            params.append(f"q={keywords.replace(' ', '%20')}")
        if params:
            search_url += "?" + "&".join(params)
        logger.info("Searching Instahyre: %s", search_url)
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3, 6)
            for p in range(max_pages):
                await human_delay(2, 4)
                cards = await page.query_selector_all(".job-card, .job-listing, [class*='job']")
                for card in cards:
                    try:
                        title_el = await card.query_selector("h3, .job-title, [class*='title']")
                        company_el = await card.query_selector(".company-name, [class*='company']")
                        loc_el = await card.query_selector(".location, [class*='location']")
                        url_el = await card.query_selector("a")
                        title = await title_el.inner_text() if title_el else ""
                        company = await company_el.inner_text() if company_el else ""
                        loc = await loc_el.inner_text() if loc_el else ""
                        url = await url_el.get_attribute("href") if url_el else ""
                        jobs.append({
                            "title": title.strip(),
                            "company": company.strip(),
                            "location": loc.strip(),
                            "url": url.strip() if url.startswith("http") else f"https://www.instahyre.com{url}",
                            "source": "instahyre",
                            "platform": "instahyre",
                        })
                    except Exception as e:
                        logger.debug("Skipping card: %s", e)
                try:
                    next_btn = await page.query_selector("a[rel='next'], .pagination .next")
                    if next_btn:
                        await next_btn.click()
                        await human_delay(2, 4)
                    else:
                        break
                except Exception:
                    break
        except Exception as e:
            logger.error("Instahyre search error: %s", e)
        finally:
            await page.close()
        logger.info("Found %d jobs on Instahyre", len(jobs))
        return jobs
