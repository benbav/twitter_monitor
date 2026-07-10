"""
One-time helper: reads the already-authenticated cookies out of the manual
login Chrome profile (storage/chrome_profile, created by logging in by hand
in a plain, non-automated Chrome window) and saves them to storage/state.json
in the format monitor.py expects.

This never touches X's login form itself, so it avoids the automation
fingerprint that flags Playwright-driven logins.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "storage" / "chrome_profile"
STATE_PATH = BASE_DIR / "storage" / "state.json"


def export():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30_000)

        if "login" in page.url:
            context.close()
            raise SystemExit("Not logged in yet in that profile -- log in manually first, then re-run this.")

        context.storage_state(path=str(STATE_PATH))
        print(f"Session exported to {STATE_PATH}")
        context.close()


if __name__ == "__main__":
    export()
