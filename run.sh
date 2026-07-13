#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

python monitor.py "$@"
