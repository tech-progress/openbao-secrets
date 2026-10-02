# Support boundary

Supported contract: one non-dev OpenBao 2.7.1 node, Raft persistence, locked gateway, declarative file audit and manual-unseal operations. This is an unpublished evaluation/small-team draft; local smoke is not production or hosted-service assurance.

Excluded: HA, multi-replica failover, KMS auto-unseal, UI, CORS browser clients, custom auth engines/plugins, privileged mlock/host guarantees, automatic audit rotation, external TLS/custodian/rekey/fresh-volume recovery verification. Do not run multiple replicas sharing Raft files. Never attach a Docker socket.

Report pinned template/app versions, health state, sanitized error codes, mount free space and timing. Never include tokens, shares, plaintext secrets, gateway keys, raw audit logs or initialization output. If `/healthz` is 200 and `/readyz` is 503 with `sealed=true`, bring the authorized share custodians; redeploying does not repair this operating state. If the backend exits, the supervisor exits so Railway can detect failure.

Investigate upstream [OpenBao](https://github.com/openbao/openbao) issues separately from wrapper/source-routing issues. Incident key custody and recovery remain the operator's responsibility.
