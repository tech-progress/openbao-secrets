import base64
import atexit
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


project = sys.argv[1]
base = "http://127.0.0.1:18422"
gate = os.environ["OPERATOR_GATE_KEY"]
custodian_state = tempfile.TemporaryDirectory(prefix="openbao-custodians-")
atexit.register(custodian_state.cleanup)


def custodian(index):
    home = os.path.join(custodian_state.name, str(index))
    os.mkdir(home, 0o700)
    commands = ["gpg", "--homedir", home, "--batch", "--pinentry-mode", "loopback"]
    subprocess.run(commands + ["--passphrase", "", "--quick-generate-key", f"Disposable OpenBao custodian {index} <custodian-{index}@example.test>", "rsa2048", "encr", "1d"], check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    public = subprocess.check_output(commands + ["--export"], timeout=10, stderr=subprocess.DEVNULL)
    assert public, "Custodian public key missing"
    return commands, base64.b64encode(public).decode()


custodians = [custodian(index) for index in range(4)]


def decrypt_for(index, ciphertext):
    decrypted = subprocess.check_output(custodians[index][0] + ["--decrypt"], input=base64.b64decode(ciphertext), timeout=15, stderr=subprocess.DEVNULL)
    assert decrypted, "Custodian could not decrypt its operator material"
    return decrypted.decode().strip()


def request(path, method="GET", payload=None, token=None, gated=True, raw=False, expected=None, gate_override=None):
    headers = {"Content-Type": "application/json"}
    if gated:
        headers["X-Template-Operator-Key"] = gate_override or gate
    if token:
        headers["X-Vault-Token"] = token
    data = payload if raw else json.dumps(payload).encode() if payload is not None else None
    query = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(query, timeout=30) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    if expected is not None:
        assert status == expected, f"{method} {path}: expected {expected}, got {status}"
    elif status >= 400:
        raise AssertionError(f"{method} {path}: unexpected HTTP {status}")
    return body if raw else json.loads(body) if body else None


def wait_alive():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            return request("/healthz")
        except (OSError, AssertionError):
            time.sleep(1)
    raise AssertionError("Backend failed to become live within 90 seconds")


def unseal(keys):
    for key in keys[:2]:
        state = request("/v1/sys/unseal", "POST", {"key": key})
    assert state["sealed"] is False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            request("/readyz")
            return
        except AssertionError:
            time.sleep(1)
    raise AssertionError("Unsealed node did not become ready")


def wait_audit(token):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if "persistent/" in request("/v1/sys/audit", token=token)["data"]:
                return
        except (AssertionError, KeyError):
            pass
        time.sleep(1)
    raise AssertionError("Declarative audit device failed to become active")


assert wait_alive() == {"process_alive": True, "initialized": False, "sealed": True}
request("/readyz", expected=503)
for path in ("/v1/sys/init", "/v1/sys/unseal", "/v1/sys/rekey/init", "/v1/sys/storage/raft/snapshot"):
    request(path, "POST", {}, gated=False, expected=403)
request("/v1/sys/init", gated=False, expected=403)
request("/v1/sys/init", gate_override="wrong-operator-key", expected=403)
request("/ui/", gated=False, expected=404)
for path in ("/v1/%73ys/init", "/v1/secret/../sys/init", "/v1/secret/%2e%2e/sys/init"):
    request(path, gated=False, expected=400)
initial = request("/v1/sys/init", "POST", {"secret_shares": 3, "secret_threshold": 2, "pgp_keys": [entry[1] for entry in custodians[:3]], "root_token_pgp_key": custodians[3][1]})
keys = [decrypt_for(index, encrypted) for index, encrypted in enumerate(initial["keys_base64"])]
root_token = decrypt_for(3, initial["root_token"])
for index, encrypted in enumerate(initial["keys_base64"]):
    denied = subprocess.run(custodians[(index + 1) % 3][0] + ["--decrypt"], input=base64.b64decode(encrypted), timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert denied.returncode != 0, "Different custodian decrypted another share"
unseal(keys)
wait_audit(root_token)
request("/v1/sys/mounts/secret", "POST", {"type": "kv", "options": {"version": "2"}}, root_token, expected=204)
request("/v1/secret/data/smoke", "POST", {"data": {"value": "before-snapshot"}}, root_token)
policy = 'path "secret/data/smoke" { capabilities = ["read"] }'
request("/v1/sys/policies/acl/smoke-read", "PUT", {"policy": policy}, root_token, expected=204)
limited = request("/v1/auth/token/create", "POST", {"policies": ["smoke-read"], "no_default_policy": True, "ttl": "10m"}, root_token)["auth"]["client_token"]
assert request("/v1/secret/data/smoke", token=limited)["data"]["data"]["value"] == "before-snapshot"
request("/v1/secret/data/smoke", "POST", {"data": {"value": "denied"}}, limited, expected=403)
request("/v1/secret/data/smoke", token=limited, gated=False, expected=403)
request("/v1/sys/mounts/transit", "POST", {"type": "transit"}, root_token, expected=204)
request("/v1/transit/keys/smoke", "POST", {}, root_token, expected=200)
plaintext = base64.b64encode(b"local-test-only").decode()
ciphertext = request("/v1/transit/encrypt/smoke", "POST", {"plaintext": plaintext}, root_token)["data"]["ciphertext"]
assert request("/v1/transit/decrypt/smoke", "POST", {"ciphertext": ciphertext}, root_token)["data"]["plaintext"] == plaintext
audits = request("/v1/sys/audit", token=root_token)
assert "persistent/" in audits["data"]
snapshot = request("/v1/sys/storage/raft/snapshot", token=root_token, raw=True)
assert len(snapshot) > 100
request("/v1/secret/data/smoke", "POST", {"data": {"value": "after-snapshot"}}, root_token)
request("/v1/sys/storage/raft/snapshot", "POST", snapshot, root_token, raw=True, expected=204)
time.sleep(2)
state = wait_alive()
if state["sealed"]:
    unseal(keys)
wait_audit(root_token)
assert request("/v1/secret/data/smoke", token=root_token)["data"]["data"]["value"] == "before-snapshot"
assert request("/v1/transit/decrypt/smoke", "POST", {"ciphertext": ciphertext}, root_token)["data"]["plaintext"] == plaintext
subprocess.run(["docker", "compose", "-p", project, "restart", "openbao"], check=True, timeout=45, stdout=subprocess.DEVNULL)
assert wait_alive() == {"process_alive": True, "initialized": True, "sealed": True}
request("/readyz", expected=503)
request("/v1/sys/init", gated=False, expected=403)
unseal(keys)
wait_audit(root_token)
assert request("/v1/secret/data/smoke", token=limited)["data"]["data"]["value"] == "before-snapshot"
request("/v1/secret/data/smoke", "POST", {"data": {"value": "denied"}}, limited, expected=403)
source_logs = subprocess.check_output(["docker", "compose", "-p", project, "logs", "--no-color", "openbao"], timeout=10)
source_audit = subprocess.check_output(["docker", "compose", "-p", project, "exec", "-T", "openbao", "cat", "/data/audit.log"], timeout=10)
source_volumes = subprocess.check_output(["docker", "volume", "ls", "--format", "{{.Name}}", "--filter", f"label=com.docker.compose.project={project}"], timeout=10).decode().splitlines()
assert len(source_volumes) == 1, "Unexpected source volume count"
subprocess.run(["docker", "compose", "-p", project, "down", "--volumes", "--remove-orphans"], check=True, timeout=90, stdout=subprocess.DEVNULL)
for source_volume in source_volumes:
    assert subprocess.run(["docker", "volume", "inspect", source_volume], timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0, "Source volume was not removed"
subprocess.run(["docker", "compose", "-p", project, "up", "-d", "--wait", "--wait-timeout", "90", "openbao"], check=True, timeout=120, stdout=subprocess.DEVNULL)
assert wait_alive() == {"process_alive": True, "initialized": False, "sealed": True}
recovery_initial = request("/v1/sys/init", "POST", {"secret_shares": 3, "secret_threshold": 2, "pgp_keys": [entry[1] for entry in custodians[:3]], "root_token_pgp_key": custodians[3][1]})
recovery_keys = [decrypt_for(index, encrypted) for index, encrypted in enumerate(recovery_initial["keys_base64"])]
recovery_root = decrypt_for(3, recovery_initial["root_token"])
assert set(keys).isdisjoint(recovery_keys), "Fresh recovery volume reused source initialization"
unseal(recovery_keys)
wait_audit(recovery_root)
request("/v1/sys/storage/raft/snapshot-force", "POST", snapshot, recovery_root, raw=True, expected=204)
deadline = time.monotonic() + 30
while time.monotonic() < deadline and not wait_alive()["sealed"]:
    time.sleep(1)
assert wait_alive()["sealed"] is True, "Snapshot force restore must return to sealed state"
unseal(keys)
wait_audit(root_token)
assert request("/v1/secret/data/smoke", token=limited)["data"]["data"]["value"] == "before-snapshot"
request("/v1/secret/data/smoke", "POST", {"data": {"value": "denied"}}, limited, expected=403)
assert request("/v1/transit/decrypt/smoke", "POST", {"ciphertext": ciphertext}, root_token)["data"]["plaintext"] == plaintext
request("/v1/sys/mounts", token=recovery_root, expected=403)
public_environment = {**os.environ, "PUBLIC_DATA_PLANE": "true"}
subprocess.run(["docker", "compose", "-p", project, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "90", "openbao"], env=public_environment, check=True, timeout=120, stdout=subprocess.DEVNULL)
assert wait_alive()["sealed"] is True
unseal(keys)
wait_audit(root_token)
request("/v1/secret/data/smoke", gated=False, expected=403)
assert request("/v1/secret/data/smoke", token=limited, gated=False)["data"]["data"]["value"] == "before-snapshot"
request("/v1/secret/data/smoke", "POST", {"data": {"value": "denied"}}, limited, gated=False, expected=403)
request("/v1/sys/init", token=root_token, gated=False, expected=403)
assert request("/v1/transit/decrypt/smoke", "POST", {"ciphertext": ciphertext}, root_token, gated=False)["data"]["plaintext"] == plaintext
request("/v1/auth/token/revoke-self", "POST", {}, root_token, expected=204)
request("/v1/sys/mounts", token=root_token, expected=403)
logs = subprocess.check_output(["docker", "compose", "-p", project, "logs", "--no-color", "openbao"], timeout=10)
audit = subprocess.check_output(["docker", "compose", "-p", project, "exec", "-T", "openbao", "cat", "/data/audit.log"], timeout=10)
assert audit
for secret in [*keys, *recovery_keys, root_token, recovery_root, limited, gate, "local-test-only", "before-snapshot", "after-snapshot"]:
    assert all(secret.encode() not in output for output in (logs, audit, source_logs, source_audit)), "Secret leaked to logs"
print("PASS: separate disposable PGP custodians, wrong-custodian denial, gated initialization, least-privilege KV, transit, audit, fresh-volume force recovery with original key lineage, sealed restart, public-data-plane denial, root revocation, no plaintext test secrets in logs.")
print("UNRUN: external HTTPS, independent human custody, compromised-key recovery, rekey/rotation, load and remote deployment gates.")
