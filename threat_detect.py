"""
Flag tweet text for threatening language or mentions of watched names.

Reads plain word/phrase lists from config/threat_words.txt and
config/watch_names.txt -- one entry per line, '#' comments and blank lines
ignored. Edit those files directly to tune what gets flagged; no code
changes needed.
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
THREAT_WORDS_PATH = CONFIG_DIR / "threat_words.txt"
WATCH_NAMES_PATH = CONFIG_DIR / "watch_names.txt"


def _load_terms(path):
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _compile_pattern(terms):
    if not terms:
        return None
    escaped = [re.escape(t).replace(r"\ ", r"\s+") for t in terms]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def load_patterns():
    """Compile the current word lists. Call once per run, before scanning tweets."""
    threat_pattern = _compile_pattern(_load_terms(THREAT_WORDS_PATH))
    name_pattern = _compile_pattern(_load_terms(WATCH_NAMES_PATH))
    return threat_pattern, name_pattern


def scan(text, threat_pattern, name_pattern):
    """Return {"threat_matches": [...], "name_matches": [...]} for the given tweet text."""
    threat_matches = sorted(set(m.lower() for m in threat_pattern.findall(text))) if threat_pattern else []
    name_matches = sorted(set(m.lower() for m in name_pattern.findall(text))) if name_pattern else []
    return {"threat_matches": threat_matches, "name_matches": name_matches}
