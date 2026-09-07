from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import BrowserContext, Playwright

LMS_BASE = "https://lms.hcmut.edu.vn"
DEFAULT_PROFILE_DIR = Path(".bk-lms-profile")
STORAGE_STATE_NAME = "storage_state.json"


def storage_state_path(profile_dir: Path) -> Path:
    return Path(profile_dir) / STORAGE_STATE_NAME


def load_storage_cookies(profile_dir: Path) -> list[dict]:
    path = storage_state_path(profile_dir)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    cookies = payload.get("cookies")
    return cookies if isinstance(cookies, list) else []


async def restore_storage_state(context: BrowserContext, profile_dir: Path) -> int:
    """Re-inject session cookies Chromium does not persist across Playwright launches."""
    cookies = load_storage_cookies(profile_dir)
    if not cookies:
        return 0
    try:
        await context.add_cookies(cookies)
    except Exception:
        return 0
    return len(cookies)


async def save_storage_state(context: BrowserContext, profile_dir: Path) -> Path:
    path = storage_state_path(profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(path))
    return path


async def launch_persistent_lms_context(
    playwright: Playwright,
    profile_dir: Path,
    *,
    headless: bool = False,
) -> BrowserContext:
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        accept_downloads=False,
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
        ],
    )
    # A restored hung tab can block later goto() calls; keep one clean page.
    pages = list(context.pages)
    page = pages[0] if pages else await context.new_page()
    for extra in pages[1:]:
        try:
            await extra.close()
        except Exception:
            pass
    try:
        await page.goto("about:blank", wait_until="commit", timeout=10_000)
    except Exception:
        pass
    await restore_storage_state(context, profile_dir)
    return context
