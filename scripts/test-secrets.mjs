import assert from "node:assert/strict";
import { evaluateRailwayFile } from "railway/iac";

const first = await evaluateRailwayFile(".railway/railway.ts");
const second = await evaluateRailwayFile(".railway/railway.ts");
const variable = result => result.desiredConfig.services.OpenBao.variables.OPERATOR_GATE_KEY;
const firstKey = variable(first);
const secondKey = variable(second);
assert.match(firstKey.value, /^[a-f0-9]{48}$/);
assert.match(secondKey.value, /^[a-f0-9]{48}$/);
assert.equal(firstKey.preserveExisting, true);
assert.equal(secondKey.preserveExisting, true);
assert.notEqual(firstKey.value, secondKey.value);
console.log("PASS: cryptographic operator-key generation, independent renders and native preserveExisting flag (secrets not printed)");
