import copy
import json
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parent.parent
mode, filename = sys.argv[1:]
config_input = json.loads(Path(filename).read_text())
config = config_input.get("data", {}).get("template", {}).get("serializedConfig", config_input.get("serializedConfig", config_input))
if isinstance(config, str):
    config = json.loads(config)
graph = json.loads(subprocess.check_output([str(root / "node_modules/.bin/railway-iac-ts"), ".railway/railway.ts"], cwd=root))
desired = {entry["name"]: entry for entry in graph["graph"]["resources"] if entry["type"] == "service"}
defaults = json.loads((root / "template-defaults.json").read_text())
descriptions = json.loads((root / "template-descriptions.json").read_text())
networking = json.loads((root / "template-networking.json").read_text())
volumes = json.loads((root / "template-volumes.json").read_text())
services = config["services"]
assert isinstance(services, (dict, list)), "Draft services must be an exported mapping or list"
service_values = services.values() if isinstance(services, dict) else services
assert len(services) == len(desired) and sorted(service["name"] for service in service_values) == sorted(desired), "Draft service set mismatch"
assert not set(config) - {"services", "name", "description", "version"}, "Unrecognized top-level draft resources require manual review"
restored = copy.deepcopy(config)
restored_values = restored["services"].values() if isinstance(restored["services"], dict) else restored["services"]
for service in restored_values:
    name = service["name"]
    expected = desired[name]
    source = {key: value for key, value in expected["source"].items() if key != "type"}
    mounts = service.get("volumeMounts", {})
    assert len(mounts) == 1 and len(expected["volumeAttachments"]) == 1, "Expected one existing volume ID; restore cannot invent an attachment"
    expected_mount = volumes[name]
    expected_mounts = {identifier: {**mount, **expected_mount} for identifier, mount in mounts.items()}
    target_network = {"serviceDomains": {"<hasDomain>": {"port": networking[name]["publicPort"]}}, "customDomains": {}, "tcpProxies": {}}
    target_variables = {key: {"defaultValue": value, "description": descriptions[name][key], "isOptional": False} for key, value in defaults[name].items()}
    expected_deploy = expected["deploy"]
    if mode == "audit":
        assert service["source"] == source, "Source repository/branch/root drift"
        assert service["build"] == expected["build"], "Build contract drift"
        assert service["deploy"] == expected_deploy, "Deployment contract drift"
        assert service["variables"] == target_variables, "Variables or description drift"
        assert service.get("networking") == target_network, "Public domain, custom domain or TCP proxy drift"
        assert mounts == expected_mounts, "Volume mount or size drift"
    elif mode == "restore":
        service.update(source=source, build=expected["build"], deploy=expected_deploy, variables=target_variables, networking=target_network, volumeMounts=expected_mounts)
    else:
        raise SystemExit("Expected audit or restore")
if mode == "restore":
    json.dump(restored, sys.stdout, indent=2)
    print()
else:
    print("PASS: offline draft source, build, deploy, variables, networking and single-volume contract")
