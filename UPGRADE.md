# Upgrade and recovery

Template SemVer is distinct from OpenBao 2.7.1. A storage/auth/routing-breaking contract change is major; compatible optional facilities are minor; fixes are patch. Never change pins without testing the exact artifact.

1. Read release-specific upstream upgrade/recovery notes and licenses. Scan both runtime images. Verify single-replica configuration and independent custodian availability.
2. Save a verified encrypted off-service Raft snapshot; archive audit records separately and protect the gateway key configuration outside the application. Record origin, version, backup checksum and key lineage without putting shares/tokens in metadata. Freeze writes if the migration demands consistency.
3. Build the new pinned image; rehearse the exact restore into a fresh isolated volume with the original key lineage, manually unseal, check KV versions, transit decryptions, policy denial and audit records. This local draft tested same-node/same-key snapshot restoration only, **not a new-volume disaster recovery**.
4. Schedule downtime with custodians. Upgrade one node. It starts sealed, `/healthz` is live and `/readyz` is unready. Unseal only through the guarded HTTPS path; verify integrity, access denials and root revocation before opening traffic.
5. Do not downgrade blindly after a storage migration. Rollback requires a compatible pinned binary plus the pre-upgrade snapshot in a separately isolated volume and the proper shares. Force snapshot restore never substitutes for missing keys. Rehearse cutover before relying on it.

Audit retention/rotation, share rekey, operator/gateway-key rotation, expired client tokens, off-service backup loss, origin change, lost custodian and compromised-root recovery remain mandatory unrun drills. Never persist shares in Railway variables to simplify restarts.
