import os
import platform
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext
from utils.logger import get_logger

logger = get_logger("browser")


class BrowserManager:
    def __init__(self, headless: bool = True, data_dir: str = None):
        self.headless = headless
        self.data_dir = Path(data_dir or os.path.abspath("./data/browser_profile"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self._context: Optional[BrowserContext] = None

    async def start(self):
        self._playwright = await async_playwright().start()

        launch_kwargs = dict(
            user_data_dir=str(self.data_dir),
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-popup-blocking",
                "--disable-sync",
            ],
            ignore_default_args=["--enable-automation"],
        )

        self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)

        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        logger.info("Browser started (headless=%s, profile=%s)", self.headless, self.data_dir)
        return self._context

    async def get_context(self) -> BrowserContext:
        if self._context is None:
            await self.start()
        return self._context

    async def new_page(self):
        ctx = await self.get_context()
        return await ctx.new_page()

    async def close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.debug("Failed to close browser context: %s", e)
            self._context = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("Failed to stop Playwright: %s", e)
            self._playwright = None
        logger.info("Browser closed")
