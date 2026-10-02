import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path


root = Path(__file__).resolve().parent.parent
environment = {**os.environ, "SOURCE_REPO": "qualification/local-only", "SOURCE_BRANCH": "release-v1", "SOURCE_ROOT_DIR": "/openbao-secrets"}
fixture = {"services": {"fixture-service-id": {"name": "OpenBao", "volumeMounts": {"fixture-volume-id": {"mountPath": "/wrong", "sizeMB": 1}}}}}
with tempfile.TemporaryDirectory(prefix="openbao-draft-test-") as temporary:
    draft = Path(temporary) / "draft.json"
    repaired = Path(temporary) / "repaired.json"
    draft.write_text(json.dumps(fixture))
    restore = subprocess.check_output(["bash", str(root / "scripts/restore-template-draft.sh"), str(draft)], env=environment)
    repaired.write_bytes(restore)
    subprocess.run(["bash", str(root / "scripts/audit-template.sh"), str(repaired)], env=environment, check=True)
    restored = json.loads(restore)
    assert restored["services"]["fixture-service-id"]["source"]["rootDirectory"] == "/openbao-secrets"
    list_fixture = {"services": [{**fixture["services"]["fixture-service-id"], "id": "synthetic-list-fixture-id"}]}
    draft.write_text(json.dumps(list_fixture))
    list_restore = subprocess.check_output(["bash", str(root / "scripts/restore-template-draft.sh"), str(draft)], env=environment)
    repaired.write_bytes(list_restore)
    subprocess.run(["bash", str(root / "scripts/audit-template.sh"), str(repaired)], env=environment, check=True)
    assert json.loads(list_restore)["services"][0]["id"] == "synthetic-list-fixture-id"
    for section, field, value in [("source", "branch", "main"), ("volumeMounts", "fixture-volume-id", {"mountPath": "/data", "sizeMB": 1}), ("networking", "tcpProxies", {"unsafe": {}}), ("variables", "OPERATOR_GATE_KEY", {"defaultValue": "literal-secret"})]:
        corrupt = copy.deepcopy(restored)
        corrupt["services"]["fixture-service-id"][section][field] = value
        draft.write_text(json.dumps(corrupt))
        audit = subprocess.run(["bash", str(root / "scripts/audit-template.sh"), str(draft)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert audit.returncode != 0, "Audit missed injected contract drift"
    fixture["services"]["fixture-service-id"]["volumeMounts"] = {}
    draft.write_text(json.dumps(fixture))
    assert subprocess.run(["bash", str(root / "scripts/restore-template-draft.sh"), str(draft)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0
print("PASS: offline restore/audit roundtrip, source/volume/network/secret drift rejection and missing-volume refusal (synthetic IDs, no cloud)")
