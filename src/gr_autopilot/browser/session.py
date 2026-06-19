from __future__ import annotations

from pathlib import Path
from typing import Any

# Playwright session management. Requires the `browser` extra (playwright +
# playwright-stealth) and a real, interactive one-time login. Not unit-tested
# (omitted from coverage); validated by integration on a machine with a display.

DEFAULT_STATE = Path("playwright/.auth/state.json")
BASE_URL = "https://www.goodreads.com"
# A signed-in marker — confirm/refine during the live-capture step.
SIGNED_IN_MARKER = "a[href*='/user/sign_out'], [id*='UserDropdown']"


def login(state_path: Path = DEFAULT_STATE) -> None:
    """One-time interactive login: opens a headed browser so you can clear Amazon
    MFA/CAPTCHA, then saves storage_state for headless reuse."""
    from playwright.sync_api import sync_playwright

    state_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{BASE_URL}/user/sign_in")
        print("Sign in through the browser window, then resume from the Playwright Inspector.")
        page.pause()  # headed-only; resumes when you click ▶ in the Inspector
        context.storage_state(path=str(state_path), indexed_db=True)
        browser.close()


def load_context(playwright: Any, state_path: Path = DEFAULT_STATE) -> Any:
    """Build a stealthed headless context from saved storage_state."""
    from playwright_stealth import Stealth

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(state_path))
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    Stealth().apply_stealth_sync(context)
    return context


def is_logged_in(page: Any) -> bool:
    """Login-health check: load the homepage and assert a signed-in marker exists."""
    page.goto(f"{BASE_URL}/")
    return page.query_selector(SIGNED_IN_MARKER) is not None
