# Deploy and Host OpenBao secrets on Railway

## About Hosting OpenBao secrets

[OpenBao](https://openbao.org) provides secret storage and cryptographic transit APIs. This unpublished single-node draft pairs a guarded API gateway with persistent Raft storage and file audit records. It runs non-development mode, with private loopback API/cluster listeners and no public UI. Initialization, unseal and administration stay operator-gated.

## Why Deploy OpenBao secrets

Use a bounded, self-contained deployment contract for small-team evaluation of KV/transit and least-privilege policies. **Operators must initialize with separately held shares and manually unseal after every restart.** A healthy process can be sealed and unavailable; this is not HA, automatic recovery, a managed vault, or a memory-lock guarantee.

## Common Use Cases

- Evaluate KV v2 versioned secrets and native policy denials.
- Evaluate transit encryption without exposing unseal/recovery operations.
- Rehearse encrypted snapshot backup and custodial recovery before real adoption.

## Dependencies for OpenBao secrets

### Deployment Dependencies

- OpenBao 2.7.1 and Python 3.13.12 images pinned by digest.
- A single persistent `/data` volume, stable HTTPS origin, generated gateway operator key and independent share custodians.
- Explicitly supplied accessible source repository, branch and directory; none has been created by this draft.
- Encrypted external backups, audit retention, on-call unseal operators and measured resource headroom. No paid services are provisioned here.

The UI is disabled. Public data-plane access is closed by default. Only turn on the narrow KV/transit/AppRole allowlist after bootstrap, policy tests and root-token revocation. HTTPS, independent share ceremony and full fresh-volume disaster recovery are publication/production blockers until actually exercised. See README and PUBLISHING for the complete contract and gates.
