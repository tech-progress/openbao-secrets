import { randomBytes } from "node:crypto";
import { defineRailway, group, project, service, volume } from "railway/iac";

const repo = process.env.SOURCE_REPO;
const branch = process.env.SOURCE_BRANCH ?? "release-v1";
const rootDir = process.env.SOURCE_ROOT_DIR ?? "/openbao-secrets";
if (!repo || !/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error("Set SOURCE_REPO to an accessible owner/repository; no distribution repository is assumed");
if (!branch || branch.includes("/")) throw new Error("SOURCE_BRANCH must be a nonempty slash-free release channel");
if (!rootDir.startsWith("/") || rootDir.includes("..")) throw new Error("SOURCE_ROOT_DIR must be an absolute repository directory, or / for a standalone repository");

export default defineRailway(() => {
  const storage = volume("OpenBao Data", { sizeMB: 5_000 });
  const openbao = service("OpenBao", {
    source: { type: "github", repo, branch, rootDirectory: rootDir },
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/healthz",
    healthcheckTimeout: 180,
    replicas: 1,
    networking: { serviceDomains: { "<hasDomain>": { port: 8080 } } },
    volumeMounts: { "/data": storage },
    env: {
      PORT: "8080",
      BAO_API_ADDR: "https://${{OpenBao.RAILWAY_PUBLIC_DOMAIN}}",
      OPERATOR_GATE_KEY: { value: randomBytes(24).toString("hex"), preserveExisting: true },
      PUBLIC_DATA_PLANE: "false",
    },
  });
  return project("OpenBao secrets", { resources: [group("Secrets", [openbao, storage])] });
});
