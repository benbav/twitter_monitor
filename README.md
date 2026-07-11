# twitter_monitor

Archives a Twitter/X account's original text posts: saves each tweet's
text/metadata to JSON. Only tweets flagged for threat words or watched names
(see `threat_detect.py`) get a screenshot, kept as evidence in
`data/threats/<handle>/`. Built with Python + Playwright. Safe to re-run
(e.g. via cron) — already-saved tweets are skipped.

Perfect for gathering court evidence for getting a restraining order against a mentally ill family member!

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # add --with-deps on a fresh Linux server
```

Create a `.env` file:

```
TWITTER_USERNAME="@your_bot_account"
TWITTER_PASSWORD="..."
TARGET_HANDLE="handle_to_monitor"
```

## Logging in

X aggressively flags Playwright-driven logins ("We've temporarily limited
your login" / "This browser or app may not be secure"), so don't automate
the login form itself. Instead:

1. Log in by hand in a plain, non-automated Chrome window using a dedicated
   profile:
   ```bash
   open -na "Google Chrome" --args \
     --user-data-dir="$(pwd)/storage/chrome_profile" \
     --no-first-run --no-default-browser-check "https://x.com/i/flow/login"
   ```
2. Log in manually, solve any verification step, then fully quit Chrome.
3. Open DevTools in that profile (Application → Storage → Cookies →
   `https://x.com`) and copy the values of `auth_token`, `ct0`, and `twid`.
4. Build `storage/state.json` from those three cookie values (see
   `export_session.py` for the attempt at automating this via
   `launch_persistent_context` — it can hang on a macOS Keychain prompt when
   decrypting Chrome's cookie store, so manual copy is the reliable path).

`storage/state.json` and `.env` are gitignored — never commit real
credentials or session cookies.

## Running

```bash
python monitor.py                       # uses TARGET_HANDLE from .env
python monitor.py some_handle           # or pass a handle explicitly
python monitor.py --limit 20 --include-retweets --include-replies
```

Output:
- `data/<handle>.json` — `{id, url, text, timestamp, screenshot, scraped_at, threat_matches, name_matches}` per tweet (`screenshot` is `null` unless the tweet was flagged)
- `data/threats/<handle>/<tweet_id>.png` + `.json` — evidence for flagged tweets only

## Deploying headless (e.g. AWS Lightsail)

Do the login step locally (it needs a display), then copy the whole project
— including `storage/state.json` — to the server:

```bash
scp -r . user@server:/path/to/twitter_monitor
```

On the server:

```bash
sudo apt-get update && playwright install --with-deps chromium
python monitor.py
```

`monitor.py` runs fully headless by default and never needs a display.
Re-run the manual login step and re-copy `storage/state.json` whenever the
session expires.
