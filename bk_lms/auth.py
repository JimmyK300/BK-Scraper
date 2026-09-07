from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

from .browser import (
    DEFAULT_PROFILE_DIR,
    LMS_BASE,
    launch_persistent_lms_context,
    save_storage_state,
)


class AuthenticationError(RuntimeError):
    pass


def credentials_from_env() -> tuple[str | None, str | None]:
    """Return BK-LMS credentials already loaded into the process environment."""
    if not os.environ.get("BK_LMS_USERNAME") or not os.environ.get("BK_LMS_PASSWORD"):
        from dotenv import load_dotenv

        load_dotenv(Path.cwd() / ".env", override=False)
        load_dotenv(override=False)
    username = os.environ.get("BK_LMS_USERNAME")
    password = os.environ.get("BK_LMS_PASSWORD")
    if bool(username) != bool(password):
        raise AuthenticationError(
            "Set both BK_LMS_USERNAME and BK_LMS_PASSWORD, or neither."
        )
    return username, password


def looks_authenticated_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == "lms.hcmut.edu.vn" and not parsed.path.startswith("/login/")


async def session_is_authenticated(page: Page) -> bool:
    # commit, not domcontentloaded: Moodle /my/ can hang DCL on a restored profile.
    await page.goto(f"{LMS_BASE}/my/", wait_until="commit", timeout=60_000)
    if not looks_authenticated_url(page.url):
        return False
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    html = (await page.content()).lower()
    if 'name="password"' in html and 'name="username"' in html:
        return False
    return "logout" in html or "thoát" in html or "/my/" in page.url


async def _cas_error_text(page: Page) -> str:
    locators = page.locator("#status.errors, #status, .errors, #msg")
    texts = [text.strip() for text in await locators.all_inner_texts() if text.strip()]
    return " ".join(texts)


async def _automatic_cas_login(page: Page, username: str, password: str) -> None:
    # Live HCMUT CAS 3.5.1 form: username, password, hidden lt/execution/_eventId,
    # submit named "submit". Moodle entry point redirects to sso.hcmut.edu.vn.
    await page.goto(
        f"{LMS_BASE}/login/index.php?authCAS=CAS",
        wait_until="commit",
        timeout=60_000,
    )
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    if looks_authenticated_url(page.url):
        if await session_is_authenticated(page):
            return

    if not urlparse(page.url).netloc.endswith("sso.hcmut.edu.vn"):
        await page.goto(
            f"{LMS_BASE}/login/index.php?authCAS=CAS",
            wait_until="commit",
            timeout=60_000,
        )
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except Exception:
            pass

    username_box = page.locator('input[name="username"]')
    password_box = page.locator('input[name="password"]')
    await username_box.first.wait_for(state="visible", timeout=30_000)
    if await username_box.count() == 0 or await password_box.count() == 0:
        raise AuthenticationError(
            f"HCMUT SSO login form was not recognized at {page.url}. "
            "The SSO flow may have changed or may require interactive authentication."
        )

    await username_box.first.fill(username)
    await password_box.first.fill(password)

    submit = page.locator(
        'input.btn-submit[name="submit"], input[name="submit"], '
        'button[type="submit"], input[type="submit"]'
    )
    if await submit.count() == 0:
        raise AuthenticationError("HCMUT SSO login form has no recognized submit control.")

    await submit.first.click()
    try:
        await page.wait_for_function(
            """() => {
                const host = location.hostname;
                const path = location.pathname;
                if (host === 'lms.hcmut.edu.vn' && !path.startsWith('/login/')) return true;
                if (host.endsWith('sso.hcmut.edu.vn') && document.querySelector('.errors, #status.errors')) return true;
                return false;
            }""",
            timeout=60_000,
        )
    except Exception:
        pass

    if urlparse(page.url).netloc.endswith("sso.hcmut.edu.vn"):
        detail = await _cas_error_text(page)
        raise AuthenticationError(
            "HCMUT SSO login did not leave the CAS form."
            + (f" {detail}" if detail else "")
        )

    if not await session_is_authenticated(page):
        raise AuthenticationError(
            "HCMUT SSO login did not establish a BK-LMS session. "
            "Credentials may be rejected, SSO may be rate-limited, or an interactive step may be required."
        )


async def authenticate_page(page: Page, *, headless: bool = False) -> None:
    if await session_is_authenticated(page):
        return

    username, password = credentials_from_env()
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
        wait_until="commit",
        timeout=60_000,
    )
    await asyncio.to_thread(input, "After login is complete, press Enter here...")
    if not await session_is_authenticated(page):
        raise AuthenticationError("Could not validate the BK-LMS session after login.")


@asynccontextmanager
async def authenticated_session(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    *,
    headless: bool = False,
) -> AsyncIterator[BrowserContext]:
    """Yield an authenticated persistent Chromium context for one CLI run."""
    async with async_playwright() as p:
        context = await launch_persistent_lms_context(
            p, profile_dir, headless=headless
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await authenticate_page(page, headless=headless)
            await save_storage_state(context, profile_dir)
            yield context
        finally:
            try:
                await save_storage_state(context, profile_dir)
            except Exception:
                pass
            await context.close()


async def ensure_authenticated_profile(
    profile_dir: Path,
    *,
    headless: bool = False,
) -> None:
    """Ensure the persistent Playwright profile has a usable BK-LMS session.

    Chromium does not write Moodle/CAS session cookies into the profile DB on
    Playwright close, so a storage_state.json snapshot is saved beside the
    profile and restored on the next launch.
    """
    async with authenticated_session(profile_dir, headless=headless):
        return
