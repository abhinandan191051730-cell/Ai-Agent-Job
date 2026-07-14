import os
import platform
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext
from utils.logger import get_logger

logger = get_logger("browser")


def _find_system_chrome() -> Optional[str]:
    candidates = []
    if platform.system() == "Windows":
        for base in [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.path.expandvars(r"%LOCALAPPDATA%"),
        ]:
            candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    elif platform.system() == "Darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        candidates.extend(["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"])

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


class BrowserManager:
    def __init__(self, headless: bool = True, data_dir: str = "./data/browser_profile"):
        self.headless = headless
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self._context: Optional[BrowserContext] = None

    async def start(self):
        self._playwright = await async_playwright().start()
        chrome_path = _find_system_chrome()

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
                "--disable-extensions",
                "--disable-default-apps",
                "--disable-popup-blocking",
                "--disable-sync",
                "--disable-translate",
            ],
            ignore_default_args=["--enable-automation"],
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )
        if chrome_path:
            launch_kwargs["executable_path"] = chrome_path
            logger.info("Using system Chrome: %s", chrome_path)
        else:
            logger.info("Using Playwright's bundled Chromium")

        self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
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
