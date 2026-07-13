"""
Build a one-line-per-threat summary from the evidence JSON files in
data/threats/<handle>/*.json, for quick scanning.

Usage:
    python summarize_threats.py               # all handles
    python summarize_threats.py zoxo_bb        # one handle
"""

import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
THREATS_DIR = BASE_DIR / "data" / "threats"
SUMMARY_PATH = THREATS_DIR / "summary.txt"


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def load_records(handle_filter=None):
    records = []
    if not THREATS_DIR.exists():
        return records
    for handle_dir in sorted(THREATS_DIR.iterdir()):
        if not handle_dir.is_dir():
            continue
        if handle_filter and handle_dir.name != handle_filter:
            continue
        for json_path in handle_dir.glob("*.json"):
            records.append(json.loads(json_path.read_text(encoding="utf-8")))
    records.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return records


def format_line(record):
    tags = []
    if record.get("threat_matches"):
        tags.append("THREAT:" + ",".join(record["threat_matches"]))
    if record.get("name_matches"):
        tags.append("NAME:" + ",".join(record["name_matches"]))
    return (
        f'{clean_text(record.get("text"))} | {record.get("timestamp")} '
        f'[{record.get("handle")}] {" ".join(tags)} | {record.get("url")}'
    )


def main():
    handle_filter = sys.argv[1] if len(sys.argv) > 1 else None
    records = load_records(handle_filter)
    lines = [format_line(r) for r in records]
    SUMMARY_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"Wrote {len(lines)} threat(s) to {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
