#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 scripts/draft.py audit "${1:?Usage: audit-template.sh EXPORTED_DRAFT_JSON (offline, no cloud calls)}"
