from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("scraper.instahyre")

SEARCH_SELECTORS = {
    "job_cards": [
        ".job-card, .job-listing, [class*='job']",
        ".card.job",
        "[class*='job-card']",
    ],
    "title": [
        "h3, .job-title, [class*='title']",
        "h2, h4",
    ],
    "company": [
        ".company-name, [class*='company']",
        "[class*='organization']",
    ],
    "location": [
        ".location, [class*='location']",
        "[class*='place']",
    ],
    "next_button": [
        "a[rel='next'], .pagination .next",
        "[aria-label='Next']",
        "a:has-text('Next')",
    ],
}

LOGIN_INDICATORS = [
    "#login-form",
    "input[name='password']",
    "input[type='password']",
    "a:has-text('Sign in')",
    "a:has-text('Log in')",
]


class InstahyreScraper:
    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.auth_required = False

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

            for indicator in LOGIN_INDICATORS:
                if await page.query_selector(indicator):
                    self.auth_required = True
                    logger.warning("Instahyre login wall detected. Marking auth_required.")
                    return jobs

            for p in range(max_pages):
                await human_delay(2, 4)
                cards = None
                for sel in SEARCH_SELECTORS["job_cards"]:
                    cards = await page.query_selector_all(sel)
                    if cards:
                        break
                if not cards:
                    break
                for card in cards:
                    try:
                        title_el = await self._find_from_card(card, SEARCH_SELECTORS["title"])
                        company_el = await self._find_from_card(card, SEARCH_SELECTORS["company"])
                        loc_el = await self._find_from_card(card, SEARCH_SELECTORS["location"])
                        url_el = await card.query_selector("a")
                        title = await title_el.inner_text() if title_el else ""
                        company = await company_el.inner_text() if company_el else ""
                        loc = await loc_el.inner_text() if loc_el else ""
                        url = await url_el.get_attribute("href") if url_el else ""
                        if url and not url.startswith("http"):
                            url = f"https://www.instahyre.com{url}"
                        jobs.append({
                            "title": title.strip(),
                            "company": company.strip(),
                            "location": loc.strip(),
                            "url": url,
                            "source": "instahyre",
                            "platform": "instahyre",
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
            logger.error("Instahyre search error: %s", e)
        finally:
            await page.close()
        logger.info("Found %d jobs on Instahyre", len(jobs))
        return jobs

    async def _find_from_card(self, card, selectors: list):
        for sel in selectors:
            el = await card.query_selector(sel)
            if el:
                return el
        return None
