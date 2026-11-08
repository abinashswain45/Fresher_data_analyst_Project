import os

from playwright.async_api import Browser, Playwright, async_playwright

from ..config import get_settings

_FALLBACK_PATHS = ["/opt/pw-browsers/chromium"]


async def launch_browser(headless: bool | None = None) -> tuple[Playwright, Browser]:
    s = get_settings()
    headless = s.automation_headless if headless is None else headless
    pw = await async_playwright().start()
    args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    try:
        if s.playwright_chromium_executable:
            browser = await pw.chromium.launch(headless=headless, executable_path=s.playwright_chromium_executable, args=args)
        else:
            try:
                browser = await pw.chromium.launch(headless=headless, args=args)
            except Exception:
                path = next((p for p in _FALLBACK_PATHS if os.path.exists(p)), None)
                if not path:
                    raise
                browser = await pw.chromium.launch(headless=headless, executable_path=path, args=args)
    except Exception:
        await pw.stop()
        raise
    return pw, browser
