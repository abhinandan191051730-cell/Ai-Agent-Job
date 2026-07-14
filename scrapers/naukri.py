from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger
from utils.exceptions import SelectorNotFoundError

logger = get_logger("scraper.naukri")

SEARCH_SELECTORS = {
    "job_cards": [
        ".jobTuple, .cust-job-tuple, article.jobTuple",
        "div[class*='job']",
        ".job-list-card",
        "[class*='jobCard']",
    ],
    "title": [
        "a.title, .title, [class*='title']",
        "a[class*='title']",
        "h2 a",
    ],
    "company": [
        "a.subTitle, .subTitle, [class*='company']",
        "a[class*='company']",
        ".company-name",
    ],
    "location": [
        "li.location, span.location, [class*='location']",
        "[class*='loc']",
        ".job-location",
    ],
    "next_button": [
        "a[title='Next']",
        ".pagination .next",
        "a:has-text('Next')",
        "[aria-label='Next']",
    ],
}

LOGIN_INDICATORS = [
    "input[name='password']",
    "#loginForm",
    ".login-layer",
    "[data-ga-track='Login']",
]


class NaukriScraper:
    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.auth_required = False

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

            for indicator in LOGIN_INDICATORS:
                if await page.query_selector(indicator):
                    self.auth_required = True
                    logger.warning("Naukri login wall detected. Marking auth_required.")
                    return jobs

            for p in range(max_pages):
                await human_delay(2, 4)
                cards = None
                for sel in SEARCH_SELECTORS["job_cards"]:
                    cards = await page.query_selector_all(sel)
                    if cards:
                        break
                if not cards:
                    logger.info("Naukri: no job cards found on page %d", p)
                    break

                for card in cards:
                    try:
                        title_el = await self._find_from_card(card, SEARCH_SELECTORS["title"])
                        company_el = await self._find_from_card(card, SEARCH_SELECTORS["company"])
                        loc_el = await self._find_from_card(card, SEARCH_SELECTORS["location"])
                        url_el = await card.query_selector("a")
                        title = ""
                        if title_el:
                            title = await title_el.get_attribute("title") or await title_el.inner_text() or ""
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
                            "description": "",
                        })
                    except Exception as e:
                        logger.debug("Skipping card: %s", e)

                next_btn = None
                for sel in SEARCH_SELECTORS["next_button"]:
                    next_btn = await page.query_selector(sel)
                    if next_btn:
                        break
                if next_btn:
                    await next_btn.click()
                    await human_delay(2, 4)
                else:
                    break

        except Exception as e:
            logger.error("Naukri search error: %s", e)
        finally:
            await page.close()
        logger.info("Found %d jobs on Naukri", len(jobs))
        return jobs

    async def _find_from_card(self, card, selectors: list):
        for sel in selectors:
            el = await card.query_selector(sel)
            if el:
                return el
        return None
