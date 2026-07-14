from utils.browser import BrowserManager
from utils.delays import human_delay
from utils.logger import get_logger

logger = get_logger("scraper.indeed")

SEARCH_SELECTORS = {
    "job_cards": [
        ".job_seen_beacon, .result, .cardOutline, td.resultContent",
        "[data-jk]",
        ".job-card",
        ".jobTitle",
    ],
    "title": [
        "h2.jobTitle a, .jobTitle a, a[data-jk]",
        "a.jobtitle",
        "h2 a",
    ],
    "company": [
        "[data-testid='text-location'], .companyName, .company_location",
        ".company",
        "[class*='company']",
    ],
    "location": [
        "[data-testid='text-location'], .companyLocation",
        ".location",
        "[class*='location']",
    ],
    "next_button": [
        "a[aria-label='Next'], a[data-testid='pagination-page-next']",
        "[aria-label='Next Page']",
        "a:has-text('Next')",
    ],
}

LOGIN_INDICATORS = [
    "input[name='password']",
    "#login-form",
    "#authwall",
    "a:has-text('Sign in')",
]


class IndeedScraper:
    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.auth_required = False

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

            for indicator in LOGIN_INDICATORS:
                if await page.query_selector(indicator):
                    self.auth_required = True
                    logger.warning("Indeed login wall detected. Marking auth_required.")
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
                        title = ""
                        if title_el:
                            title = await title_el.get_attribute("title") or await title_el.inner_text() or ""
                        url = await title_el.get_attribute("href") if title_el else ""
                        company = await company_el.inner_text() if company_el else ""
                        loc = await loc_el.inner_text() if loc_el else ""
                        if url and not url.startswith("http"):
                            url = f"https://in.indeed.com{url}"
                        jobs.append({
                            "title": title.strip(),
                            "company": company.strip(),
                            "location": loc.strip(),
                            "url": url,
                            "source": "indeed",
                            "platform": "indeed",
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
            logger.error("Indeed search error: %s", e)
        finally:
            await page.close()
        logger.info("Found %d jobs on Indeed", len(jobs))
        return jobs

    async def _find_from_card(self, card, selectors: list):
        for sel in selectors:
            el = await card.query_selector(sel)
            if el:
                return el
        return None
