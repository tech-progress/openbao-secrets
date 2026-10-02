#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for path in Dockerfile app.py tests.py .env.example .railway/railway.ts bun.lock VERSION CHANGELOG.md README.md MARKETPLACE.md PUBLISHING.md SUPPORT.md UPGRADE.md LICENSE_REVIEW.md FINDINGS.md compose.yaml template-defaults.json template-descriptions.json template-networking.json template-volumes.json marketplace-metadata.json scripts/smoke.sh scripts/smoke.py scripts/audit-template.sh scripts/restore-template-draft.sh; do test -f "${path}"; done
version="$(cat VERSION)"
[[ "${version}" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
grep -Fq "## [${version}] - " CHANGELOG.md
for script in scripts/*.sh; do bash -n "${script}"; done
for file in template-*.json marketplace-metadata.json; do jq empty "${file}"; done
python3 -m unittest tests.py
python3 scripts/test-draft.py
SOURCE_REPO=qualification/local-only node scripts/test-secrets.mjs
OPERATOR_GATE_KEY=verify-only-not-a-deployed-secret-000000 BAO_API_ADDR=http://127.0.0.1:18422 docker compose config --quiet
SOURCE_REPO="${SOURCE_REPO:-qualification/local-only}" SOURCE_BRANCH="${SOURCE_BRANCH:-release-v1}" SOURCE_ROOT_DIR="${SOURCE_ROOT_DIR:-/openbao-secrets}" ./node_modules/.bin/railway-iac-ts .railway/railway.ts | python3 -c 'import json,sys; graph=json.load(sys.stdin); service=next(resource for resource in graph["graph"]["resources"] if resource["type"]=="service"); assert graph["ok"] and service["source"]["rootDirectory"].startswith("/") and service["deploy"]["healthcheckPath"]=="/healthz"; assert len(service["volumeAttachments"])==1 and service["variables"]["PUBLIC_DATA_PLANE"]["value"]=="false"; assert service["networking"]["serviceDomains"]["<hasDomain>"]["port"]==8080'
python3 -c 'import json; from pathlib import Path; defaults=json.loads(Path("template-defaults.json").read_text()); descriptions=json.loads(Path("template-descriptions.json").read_text()); assert defaults.keys()==descriptions.keys(); assert all(defaults[name].keys()==descriptions[name].keys() for name in defaults); metadata=json.loads(Path("marketplace-metadata.json").read_text()); assert 45<=len(metadata["description"])<=75 and "id" not in metadata and "code" not in metadata'
! find . -path './node_modules' -prune -o -type f \( -name .env -o -name '*.local' \) -print | grep .
grep -Fq '2.7.1@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf' Dockerfile
echo 'PASS: local structure, version, unit tests, source contract, Compose, metadata and fail-closed defaults. Build/smoke and operator gates are separate.'
