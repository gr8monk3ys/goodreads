from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Playwright session management. Requires the `browser` extra. Integration-only
# (omitted from unit coverage); the config here is VERIFIED against the live site:
# stealth + a realistic fingerprint are mandatory (plain headless is 403'd by AWS WAF).

DEFAULT_STATE = Path("playwright/.auth/state.json")
BASE_URL = "https://www.goodreads.com"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def login(state_path: Path = DEFAULT_STATE) -> None:
    """One-time interactive login: opens a headed browser so a human clears Amazon
    MFA/CAPTCHA, then saves storage_state. Resume via the Playwright Inspector."""
    from playwright.sync_api import sync_playwright

    state_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"{BASE_URL}/user/sign_in")
        print("Sign in, then click Resume in the Playwright Inspector window.")
        page.pause()
        ctx.storage_state(path=str(state_path), indexed_db=True)
        browser.close()


@contextmanager
def authed_page(
    state_path: Path = DEFAULT_STATE, *, headless: bool = True
) -> Iterator[Any]:
    """Yield a stealthed, storage_state-authenticated Page.

    Stealth + a realistic UA/viewport/locale/timezone are REQUIRED — plain headless
    Chromium is 403'd by AWS WAF (verified live).
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            storage_state=str(state_path),
            user_agent=_UA,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            timezone_id="America/Los_Angeles",
        )
        page = ctx.new_page()
        try:
            yield page
        finally:
            browser.close()


def is_logged_in(page: Any) -> bool:
    """Login-health check. Loads an auth-required page; a WAF 403 counts as NOT logged in."""
    page.goto(f"{BASE_URL}/review/list", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if "403" in (page.title() or ""):
        return False
    return "sign_in" not in page.url and "/ap/signin" not in page.url
