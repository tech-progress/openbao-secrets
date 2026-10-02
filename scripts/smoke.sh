#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
project="openbao-smoke-$(date +%s)-${RANDOM}"
export OPERATOR_GATE_KEY="$(openssl rand -hex 24)"
export BAO_API_ADDR=http://127.0.0.1:18422 PUBLIC_DATA_PLANE=false
python3 -c 'import socket; listener = socket.socket(); listener.bind(("127.0.0.1", 18422)); listener.close()'
cleanup() {
  status=$?
  trap - EXIT
  if ! timeout 90 docker compose -p "${project}" down --volumes --remove-orphans --rmi local >/dev/null; then status=1; fi
  if [[ -n "$(docker ps -aq --filter "label=com.docker.compose.project=${project}")$(docker volume ls -q --filter "label=com.docker.compose.project=${project}")$(docker network ls -q --filter "label=com.docker.compose.project=${project}")" ]]; then
    echo "Owned OpenBao resources remain: ${project}" >&2
    status=1
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
timeout 300 docker compose -p "${project}" build
timeout 60 docker compose -p "${project}" run --rm --no-deps --entrypoint python openbao tests.py
if ! docker compose -p "${project}" up -d --wait --wait-timeout 120; then
  docker compose -p "${project}" logs --no-color openbao
  exit 1
fi
if ! timeout 300 python3 scripts/smoke.py "${project}"; then
  docker compose -p "${project}" logs --no-color openbao
  exit 1
fi
docker compose -p "${project}" ps --format json
docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' "$(docker compose -p "${project}" ps -q openbao)"
