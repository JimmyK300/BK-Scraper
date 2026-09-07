from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright

from .crawler import LMS_BASE


class AuthenticationError(RuntimeError):
    pass


def credentials_from_env() -> tuple[str | None, str | None]:
    """Return BK-LMS credentials already loaded into the process environment."""
    username = os.environ.get("BK_LMS_USERNAME")
    password = os.environ.get("BK_LMS_PASSWORD")
    if bool(username) != bool(password):
        raise AuthenticationError(
            "Set both BK_LMS_USERNAME and BK_LMS_PASSWORD, or neither."
        )
    return username, password


def _looks_authenticated_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.netloc == "lms.hcmut.edu.vn"
        and parsed.path not in {"/login/index.php", "/login/"}
    )


async def _session_is_authenticated(page: Page) -> bool:
    await page.goto(f"{LMS_BASE}/my/", wait_until="domcontentloaded")
    if not _looks_authenticated_url(page.url):
        return False
    html = (await page.content()).lower()
    if 'name="password"' in html and 'name="username"' in html:
        return False
    return "logout" in html or "/my/" in page.url


async def _automatic_cas_login(page: Page, username: str, password: str) -> None:
    # BK-LMS exposes HCMUT SSO through Moodle's CAS auth entry point. The CAS
    # form currently uses the conventional username/password field names.
    await page.goto(
        f"{LMS_BASE}/login/index.php?authCAS=CAS",
        wait_until="domcontentloaded",
    )

    if await _session_is_authenticated(page):
        return

    # Re-enter CAS after the session check above because that check visits /my/.
    await page.goto(
        f"{LMS_BASE}/login/index.php?authCAS=CAS",
        wait_until="domcontentloaded",
    )

    username_box = page.locator('input[name="username"]')
    password_box = page.locator('input[name="password"]')
    if await username_box.count() == 0 or await password_box.count() == 0:
        raise AuthenticationError(
            f"HCMUT SSO login form was not recognized at {page.url}. "
            "The SSO flow may have changed or may require interactive authentication."
        )

    await username_box.first.fill(username)
    await password_box.first.fill(password)

    submit = page.locator(
        'input[name="submit"], button[type="submit"], input[type="submit"]'
    )
    if await submit.count() == 0:
        raise AuthenticationError("HCMUT SSO login form has no recognized submit control.")

    await submit.first.click()
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except Exception:
        # A later explicit /my/ validation decides whether login succeeded.
        pass

    if not await _session_is_authenticated(page):
        raise AuthenticationError(
            "HCMUT SSO login did not establish a BK-LMS session. "
            "Credentials may be rejected, SSO may be rate-limited, or an interactive step may be required."
        )


async def ensure_authenticated_profile(
    profile_dir: Path,
    *,
    headless: bool = False,
) -> None:
    """Ensure the persistent Playwright profile has a usable BK-LMS session.

    When BK_LMS_USERNAME/BK_LMS_PASSWORD are present, authentication is
    attempted automatically. Without them, a headed run preserves the old
    manual-login fallback. Secrets never leave process memory or the local
    browser profile.
    """
    username, password = credentials_from_env()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            accept_downloads=False,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            if await _session_is_authenticated(page):
                return

            if username and password:
                await _automatic_cas_login(page, username, password)
                return

            if headless:
                raise AuthenticationError(
                    "BK-LMS session is not authenticated and no credentials are configured. "
                    "Create a local .env or run once without --headless and log in manually."
                )

            print("\nBK-LMS needs authentication.")
            print("Log in in the opened browser window.")
            await page.goto(
                f"{LMS_BASE}/login/index.php?authCAS=CAS",
                wait_until="domcontentloaded",
            )
            await asyncio.to_thread(input, "After login is complete, press Enter here...")
            if not await _session_is_authenticated(page):
                raise AuthenticationError("Could not validate the BK-LMS session after login.")
        finally:
            await context.close()
