import test from "node:test";
import assert from "node:assert/strict";
import { doctorSafety } from "../src/doctor.js";

test("doctor reports reachable active side effects consistently", () => {
  const result = doctorSafety({ task: { enrolled: true } }, { runEnabled: true }, true);
  assert.equal(result.status, "ACTIVE_READY");
  assert.equal(result.safety.sendsEnabled, true);
  assert.equal(result.safety.turnsEnabled, true);
});

test("doctor reports observe safety while any active gate is closed", () => {
  const result = doctorSafety({ task: { enrolled: true } }, { runEnabled: false }, true);
  assert.equal(result.status, "OBSERVE_READY");
  assert.equal(result.safety.sendsEnabled, false);
  assert.equal(result.safety.turnsEnabled, false);
});
