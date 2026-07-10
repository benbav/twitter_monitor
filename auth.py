"""
One-time (or occasional) interactive login.

Run this with a real display (your local Mac), NOT on the headless server:

    python auth.py

It opens a visible browser, logs into X/Twitter with the credentials from
.env, lets you solve any captcha/verification-code challenge by hand, then
saves the authenticated session to storage/state.json.

Copy that state.json to the server (e.g. via scp) and monitor.py will reuse
it headlessly from then on. Re-run this script and re-copy whenever the
session expires or X forces a re-login.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "storage" / "state.json"

load_dotenv(BASE_DIR / ".env")

USERNAME = os.environ.get("TWITTER_USERNAME")
PASSWORD = os.environ.get("TWITTER_PASSWORD")


def login():
    if not USERNAME or not PASSWORD:
        sys.exit("Set TWITTER_USERNAME and TWITTER_PASSWORD in .env first.")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://x.com/i/flow/login")

        try:
            page.get_by_label("Phone, email, or username").fill(USERNAME.lstrip("@"))
            page.get_by_role("button", name="Next").click()

            # X sometimes inserts an extra "confirm your identifier" step.
            confirm_input = page.locator('input[data-testid="ocfEnterTextTextInput"]')
            if confirm_input.count():
                confirm_input.fill(USERNAME.lstrip("@"))
                page.get_by_role("button", name="Next").click()

            page.get_by_label("Password", exact=False).fill(PASSWORD)
            page.get_by_role("button", name="Log in").click()
        except Exception as e:
            print(f"Automated login step didn't match the page ({e}).")
            print("Finish logging in manually in the browser window that opened.")

        print("If a verification code / captcha screen appears, solve it now in the browser window.")
        page.wait_for_url("https://x.com/home", timeout=180_000)

        context.storage_state(path=str(STATE_PATH))
        print(f"Session saved to {STATE_PATH}")
        browser.close()


if __name__ == "__main__":
    login()
