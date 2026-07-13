"""
Scrape a Twitter/X profile's original text posts, saving text/metadata to a
JSON file. Only tweets flagged by threat_detect (threat words or watched
names) get a screenshot, saved as evidence under data/threats/<handle>/.
Safe to re-run on a schedule (e.g. cron) -- already-saved tweets are skipped.

Requires storage/state.json to exist first (see auth.py). Runs fully
headless by default, so it's fine on a server with no display.

Usage:
    python monitor.py <handle> [--limit 20] [--include-retweets] [--include-replies] [--headed]
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import alert_email
import threat_detect

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "storage" / "state.json"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
THREATS_LOG_PATH = LOGS_DIR / "threats.log"
THREATS_DIR = DATA_DIR / "threats"
ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.exists():
    ENV_PATH.write_text((BASE_DIR / ".env.example").read_text())
    sys.exit(f"Created {ENV_PATH} from template -- fill in your credentials, then re-run.")

load_dotenv(ENV_PATH)


def load_existing(handle):
    path = DATA_DIR / f"{handle}.json"
    if path.exists():
        return {t["id"]: t for t in json.loads(path.read_text())}
    return {}


def save_all(handle, tweets_by_id):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{handle}.json"
    ordered = sorted(tweets_by_id.values(), key=lambda t: int(t["id"]), reverse=True)
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False))


def log_flagged_tweet(record, flags):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    tags = []
    if flags["threat_matches"]:
        tags.append("THREAT flags=" + ",".join(flags["threat_matches"]))
    if flags["name_matches"]:
        tags.append("NAME flags=" + ",".join(flags["name_matches"]))
    line = (
        f'{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} '
        f'[{record["handle"]}] {" | ".join(tags)} '
        f'url={record["url"]} text="{record["text"]}"\n'
    )
    with THREATS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)
    print(f"FLAGGED tweet {record['id']}: {' | '.join(tags)}")


def save_threat_evidence(handle, record, article):
    """Screenshot a flagged tweet and save it plus its metadata under
    data/threats/<handle>/. This is the only place tweets get screenshotted.

    Filenames are date-prefixed (from scraped_at) so a plain alphabetical sort
    -- e.g. in a file browser -- doubles as a chronological sort."""
    evidence_dir = THREATS_DIR / handle
    evidence_dir.mkdir(parents=True, exist_ok=True)
    date_prefix = record["scraped_at"].replace(":", "-")
    base_name = f"{date_prefix}_{record['id']}"
    screenshot_path = evidence_dir / f"{base_name}.png"
    article.scroll_into_view_if_needed()
    article.screenshot(path=str(screenshot_path))
    record["screenshot"] = str(screenshot_path.relative_to(BASE_DIR))
    (evidence_dir / f"{base_name}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False)
    )
    return screenshot_path


def extract_tweet_id(article):
    links = article.locator('a[href*="/status/"]')
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href") or ""
        m = re.search(r"/status/(\d+)", href)
        if m:
            return m.group(1)
    return None


def is_retweet(article):
    ctx = article.locator('[data-testid="socialContext"]')
    if ctx.count():
        text = ctx.first.inner_text().lower()
        return "repost" in text or "retweet" in text
    return False


def is_reply(article):
    try:
        head = article.inner_text(timeout=1000).lstrip()
    except PWTimeout:
        return False
    return head.startswith("Replying to")


def scrape(handle, limit, max_scrolls, headless, include_retweets, include_replies):
    if not STATE_PATH.exists():
        sys.exit("No saved session found at storage/state.json. Run auth.py first (with a display) and copy it here.")

    existing = load_existing(handle)
    threat_pattern, name_pattern = threat_detect.load_patterns()

    new_records = {}

    try:
        _scrape_inner(
            handle, limit, max_scrolls, headless, include_retweets, include_replies,
            existing, threat_pattern, name_pattern, new_records,
        )
    finally:
        if new_records:
            existing.update(new_records)
            save_all(handle, existing)

    print(f"Done. {len(new_records)} new tweet(s) saved for @{handle}.")


def _scrape_inner(
    handle, limit, max_scrolls, headless, include_retweets, include_replies,
    existing, threat_pattern, name_pattern, new_records,
):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded")

        if "login" in page.url or "flow/login" in page.url:
            debug_shot = LOGS_DIR / "session_expired_debug.png"
            try:
                page.screenshot(path=str(debug_shot), full_page=True)
            except Exception as e:
                print(f"Could not capture debug screenshot: {e}")
            print(f"Redirected to: {page.url}")
            browser.close()
            alert_email.send_session_expired_alert(handle)
            sys.exit("Session expired (redirected to login). Re-run auth.py or export_session.py and copy the new storage/state.json here.")

        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=30_000)
        except PWTimeout:
            browser.close()
            sys.exit(f"No tweets found for @{handle} (profile empty/protected, login expired, or X changed its markup).")

        stale_scrolls = 0
        for _ in range(max_scrolls):
            if len(new_records) >= limit:
                break

            articles = page.locator('article[data-testid="tweet"]')
            count = articles.count()
            found_new_this_pass = False

            for i in range(count):
                if len(new_records) >= limit:
                    break
                article = articles.nth(i)
                try:
                    tweet_id = extract_tweet_id(article)
                    if not tweet_id or tweet_id in existing or tweet_id in new_records:
                        continue

                    if is_retweet(article) and not include_retweets:
                        continue
                    if is_reply(article) and not include_replies:
                        continue

                    text_el = article.locator('[data-testid="tweetText"]')
                    text = text_el.first.inner_text() if text_el.count() else ""
                    if not text.strip():
                        continue  # media-only post, not a text post

                    time_el = article.locator("time").first
                    timestamp = time_el.get_attribute("datetime") if time_el.count() else None
                except Exception as e:
                    print(f"Skipping a tweet (stale/detached element while reading content): {e}")
                    continue

                flags = threat_detect.scan(text, threat_pattern, name_pattern)

                record = {
                    "id": tweet_id,
                    "handle": handle,
                    "url": f"https://x.com/{handle}/status/{tweet_id}",
                    "text": text,
                    "timestamp": timestamp,
                    "screenshot": None,
                    "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "threat_matches": flags["threat_matches"],
                    "name_matches": flags["name_matches"],
                }
                new_records[tweet_id] = record
                found_new_this_pass = True
                print(f"Saved tweet {tweet_id}")

                if flags["threat_matches"] or flags["name_matches"]:
                    try:
                        screenshot_path = save_threat_evidence(handle, record, article)
                    except Exception as e:
                        print(f"Could not screenshot flagged tweet {tweet_id}: {e}")
                        screenshot_path = None
                    log_flagged_tweet(record, flags)
                    alert_email.send_threat_alert(record, flags, screenshot_path)

            stale_scrolls = 0 if found_new_this_pass else stale_scrolls + 1
            if stale_scrolls >= 4:
                break

            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)

        # Refresh cookies (they rotate) so the session stays valid longer.
        context.storage_state(path=str(STATE_PATH))
        browser.close()


def main():
    default_handle = os.environ.get("TARGET_HANDLE", "").lstrip("@") or None

    parser = argparse.ArgumentParser(description="Archive a Twitter/X account's text posts, screenshotting only flagged (threat/name) tweets.")
    parser.add_argument(
        "handle",
        nargs="?",
        default=default_handle,
        help="Twitter/X handle without the @ (defaults to TARGET_HANDLE in .env)",
    )
    parser.add_argument("--limit", type=int, default=20, help="Max new tweets to capture this run")
    parser.add_argument("--max-scrolls", type=int, default=30, help="Safety cap on timeline scroll iterations")
    parser.add_argument("--headed", action="store_true", help="Show the browser window (for local debugging only)")
    parser.add_argument("--include-retweets", action="store_true")
    parser.add_argument("--include-replies", action="store_true")
    args = parser.parse_args()

    if not args.handle:
        sys.exit("No handle given and TARGET_HANDLE not set in .env.")

    print(f'=== Run started {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} ===')

    scrape(
        handle=args.handle,
        limit=args.limit,
        max_scrolls=args.max_scrolls,
        headless=not args.headed,
        include_retweets=args.include_retweets,
        include_replies=args.include_replies,
    )


if __name__ == "__main__":
    main()
