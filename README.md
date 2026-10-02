# OpenBao secrets on Railway (unpublished draft)

The current template release is `v1.0.0`. This is a **single-node, operator-managed evaluation/small-team recipe**, not an HA service or a one-click initialized secrets vault. [OpenBao](https://openbao.org) is the main product; [upstream source and MPL-2.0 license](https://github.com/openbao/openbao/tree/v2.7.1) are separate from HashiCorp Vault. A Python standard-library gateway and OpenBao run together so the API and cluster listeners can remain loopback-only without relying on cross-service disks.

## Contract and pins

- OpenBao `2.7.1`, `ghcr.io/openbao/openbao:2.7.1@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf`.
- Python `3.13.12`, Alpine `3.23`, `python:3.13.12-alpine3.23@sha256:bb1f2fdb1065c85468775c9d680dcd344f6442a2d1181ef7916b60a623f11d40`. No pip or third-party runtime packages. Image OS dependencies are captured by the immutable digest; vulnerability scanning remains a release gate.
- Local authoring dependency `railway=3.6.0`, with `bun.lock`. Use `bun install --frozen-lockfile`.
- Railway builds this directory's `Dockerfile`; its exact start command is `python /opt/template/app.py` via image entrypoint. It starts `bao server -config=/tmp/openbao-config.hcl`, **never development mode**. Backend `127.0.0.1:8200` and cluster `127.0.0.1:8201` are not exposed. Only gateway `PORT=8080` has a service domain. No Docker socket, no second service sharing this disk, no backend TCP proxy.
- One replica, one `/data` volume (5 GB starting allocation): `/data/raft` and `/data/audit.log`. The wrapper prepares only the mount directory as root, then drops to UID/GID `10001` before either long-running process. Core dumps disabled. This is not a memory-lock, no-swap, dedicated-host or confidential-computing guarantee.

## Required configuration

| Variable | Required/default | Meaning |
| --- | --- | --- |
| `BAO_API_ADDR` | Required | Stable gateway HTTPS origin, for example `https://secrets.example.com`. Only `localhost`/`127.0.0.1` may use HTTP for isolated tests. No credentials, query or path. IaC references the generated service domain; finalize any custom domain before onboarding clients. |
| `OPERATOR_GATE_KEY` | Required; generated 48 characters in draft metadata | Template gateway key, random ASCII at least 32 characters, no whitespace. This is **not** an OpenBao token or share. Missing/short keys stop startup. Send as `X-Template-Operator-Key`. Never distribute it to application clients. |
| `PUBLIC_DATA_PLANE` | `false` | Default denies every `/v1/` request without the operator gate, even requests carrying native tokens. Deliberately changing to `true` permits only `/v1/secret/*`, `/v1/transit/*`, and exact `/v1/auth/approle/login`; **native OpenBao policies/auth still apply**. All `sys`, token issuance, mount setup and recovery operations stay gated. |
| `PORT` | `8080` | Gateway listen port, not 8200 or 8201. |

Authoring-only source controls: `SOURCE_REPO` is required `owner/repository` and must actually exist and be accessible to Railway; `SOURCE_BRANCH` defaults to `release-v1` (no slash); `SOURCE_ROOT_DIR` defaults to `/openbao-secrets` and may be `/` for a real standalone distribution. The SDK field is `source.rootDirectory`. These are render-time controls, not upstream app variables. No distribution repository, template ID, deployment code or release branch has been provisioned here. Do not copy the verifier's `qualification/local-only` fixture into a draft.

Direct IaC uses Node cryptographic entropy for the gateway key and emits the native `preserveExisting=true` flag. The pinned SDK's `ctx.randomString` is deterministic and is deliberately **not** used for secrets. Template draft restore instead installs Railway's generator expression from `template-defaults.json`. Treat direct rendered graphs as sensitive: they contain a prospective gateway key and must not be published or copied to ordinary logs. Existing-secret preservation is locally serialized/tested, not live-platform verified; inspect and preserve your existing gateway key before any real apply or upgrade.

## Health is not readiness

`GET /healthz` returns HTTP 200 **when the OpenBao process responds**, including uninitialized/sealed states, with truthful `initialized` and `sealed` booleans. Railway must use this liveness endpoint to keep an intentionally sealed deployment available for an operator. `GET /readyz` returns 503 until initialized **and** unsealed; use it for application dependency monitoring. A green Railway deployment health check is not evidence that secrets can be served. Both endpoints return only these state flags, never tokens or shares.

The UI is disabled, including its native listener. There is no public administration screen. All API administration requires the independent gateway key plus native OpenBao authorization where upstream requires it. Initialization and unseal have no native login by design; the gateway closes that first-claim/recovery boundary. Paths containing percent escapes, backslashes, double slashes or dot segments are rejected instead of normalized ambiguously. Gateway strips its own key and caller forwarding headers; it does not log requests, bodies or tokens. It does not perform user-facing CORS or OIDC authentication. Do not treat it as a WAF.

## Operator initialization and custody (mandatory human gate)

1. Keep `PUBLIC_DATA_PLANE=false`; verify anonymous `/v1/sys/init` and `/v1/sys/unseal` are denied from outside. Complete a stable HTTPS/domain/TLS check before sending any real bootstrap material.
2. Use a trusted workstation and secure client, with the gateway key held in a mode-0600 client configuration (or prompted in memory), not a URL. The pinned `bao` CLI supports `-header=X-Template-Operator-Key=...` but arguments can be process-visible: use a secure workstation and do not paste this into shell history, CI or tickets. Prefer a protected client/curl configuration. Native `/v1/sys/init` accepts `secret_shares`, `secret_threshold`, `pgp_keys`, and `root_token_pgp_key`; the upstream CLI supports `-pgp-keys` and `-root-token-pgp-key`. **Arrange multiple independent custodians and PGP public keys before initializing.** The recipe does not choose a custody policy for you.
3. Store each encrypted initialization result with its respective custodian; keep decrypted unseal shares and initial root material **outside service variables, container disks, Railway logs, repositories, shell arguments and ordinary logs**. Do not redirect raw init output to deployment logs. Unseal by having custodians submit shares individually through the protected HTTPS gate. Do not serialize an unattended unseal script, `BAO_TOKEN` containing the root token, or shares into Railway environment variables. Losing the threshold is unrecoverable; a Raft snapshot does not replace it.
4. Confirm `/readyz` is 200. Static HCL configuration activates the `persistent` file audit device at `/data/audit.log`; verify `/v1/sys/audit` as an authorized operator before writing secrets. Preserve HMAC audit defaults; do not enable raw-secret logging. OpenBao 2.7 disables arbitrary API audit creation by default; this recipe uses **declarative audit**, not an invented environment flag.
5. Enable a KV v2 engine at `secret/`, a transit engine at `transit/`, and appropriate native auth engines/policies. Do not give workloads root tokens or the gateway key. Test read/write separation, denied paths, token expiry and rotation. Then revoke the initial root token once a tested operator policy and recovery plan exist. Only afterwards optionally enable the narrow public data plane; system paths stay operator-gated.
6. Each restart comes up **sealed**. Custodians must return to unseal manually before secrets are available. There is no auto-unseal promise; a KMS/HA variant is outside this contract. Plan on-call coverage and do not enable autoscaling or multiple replicas.

Read upstream [init](https://openbao.org/docs/commands/operator/init/), [unseal](https://openbao.org/docs/commands/operator/unseal/), [Raft storage](https://openbao.org/docs/configuration/storage/raft/), [listeners](https://openbao.org/docs/configuration/listener/tcp/), and [declarative audit](https://openbao.org/docs/configuration/audit/). This template does not automate a production custody ceremony.

## Local verification

```sh
bun install --frozen-lockfile
./scripts/verify.sh
./scripts/smoke.sh
```

Requires Docker Compose, Python 3, Bun, jq and OpenSSL. Smoke creates a unique Compose project, builds the same entrypoint Railway uses, binds **only** `127.0.0.1:18422`, and removes only that project's containers/network/volumes. It initializes an empty disposable node using three test shares/two required shares held solely in the host test process's memory, unseals, tests KV/transit and native policy denial, snapshots/restores the same node with the same keys, restarts, confirms sealed liveness/unready status, unseals again and revokes root. Nothing generated is a production credential. This is not external HTTPS, independent-custodian, fresh-volume disaster recovery, rekey or compromised-key recovery evidence.

Manual local startup: securely set `OPERATOR_GATE_KEY` and `BAO_API_ADDR=http://127.0.0.1:18422`, then `docker compose up --build --wait --wait-timeout 120`. The `.env.example` leaves the key blank intentionally. Do not use `down --volumes` against real data.

## Backups and restore

- Take authenticated Raft snapshots via `GET /v1/sys/storage/raft/snapshot` through the operator gate to **encrypted off-service backup storage**. Keep timestamp, checksum, pinned app/template version and origin separately. Do not copy live Raft files as a backup. Snapshot responses stream; restore accepts Content-Length bodies up to 5 GiB, with no chunked uploads. Normal requests/responses are capped at 16 MiB. Keep encrypted, verified backups substantially below the storage allocation.
- Keep custodians' shares separate from snapshots, and protect gateway/operator client credentials separately. If restoring a snapshot with another key lineage, the original snapshot's shares/seal keys are still required; `snapshot-force` bypasses a key check, not decryption requirements.
- Restore into a separately isolated single-replica node with a new volume, keep its data plane closed, verify the right key lineage, unseal, prove KV versions, transit decryption, policy denial and audit continuity, and only then switch traffic. **Fresh-volume/key-lineage and custodial recovery drills remain unrun and block production approval.** See `UPGRADE.md`.
- Audit files are not included in a Raft snapshot. Archive them off-service securely, rotate via the documented audit-file lifecycle and test reopen/restart; do not truncate blindly. The default local file has no automatic rotation. Watch free space: an unwritable audit device can stop useful requests. Budget retention and scheduled encrypted backups before production.

See `PUBLISHING.md` for offline draft tooling, `SUPPORT.md` for the support boundary, and `FINDINGS.md` for actual evidence and blockers.
