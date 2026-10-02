#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 scripts/draft.py restore "${1:?Usage: restore-template-draft.sh EXPORTED_DRAFT_JSON > repaired.json (offline only)}"
