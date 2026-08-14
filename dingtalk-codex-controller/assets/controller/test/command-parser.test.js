import test from "node:test";
import assert from "node:assert/strict";
import { parseCommand } from "../src/command-parser.js";

test("parses the exact command grammar", () => {
  assert.deepEqual(parseCommand(" /codex help "), { kind: "command", command: "help" });
  assert.deepEqual(parseCommand("/codex status"), { kind: "command", command: "status" });
  assert.deepEqual(parseCommand("/codex run health-check"), { kind: "command", command: "run", actionAlias: "health-check" });
  assert.deepEqual(parseCommand("/codex result REQ-20260813120000-a1b2c3d4"), {
    kind: "command", command: "result", requestId: "REQ-20260813120000-a1b2c3d4"
  });
});

test("parses task listing and targeted multi-line instructions", () => {
  assert.deepEqual(parseCommand("/codex threads"), { kind: "command", command: "threads", page: 1 });
  assert.deepEqual(parseCommand("/codex threads 12"), { kind: "command", command: "threads", page: 12 });
  assert.deepEqual(parseCommand("/codex send 00000000-0000-0000-0000-000000000011 inspect status\nthen report"), {
    kind: "command",
    command: "send",
    targetThreadId: "00000000-0000-0000-0000-000000000011",
    instruction: "inspect status\nthen report"
  });
  assert.deepEqual(parseCommand("/codex send 2 inspect status"), {
    kind: "command", command: "send", targetSelector: "2", instruction: "inspect status"
  });
  assert.deepEqual(parseCommand('/codex send "Task With Spaces" inspect status'), {
    kind: "command", command: "send", targetSelector: "Task With Spaces", instruction: "inspect status"
  });
});

test("rejects invalid task pages and over-limit instructions", () => {
  assert.throws(() => parseCommand("/codex threads 0"), { code: "COMMAND_INVALID" });
  assert.throws(() => parseCommand("/codex threads 1000"), { code: "COMMAND_INVALID" });
  assert.throws(() => parseCommand(`/codex send 00000000-0000-0000-0000-000000000011 ${"x".repeat(1001)}`), { code: "INSTRUCTION_TOO_LONG" });
});

test("parses binding, monitoring, queue and bound-target commands", () => {
  assert.deepEqual(parseCommand("/codex bind 示例任务-执行"), {
    kind: "command", command: "target", targetSelector: "示例任务-执行"
  });
  assert.deepEqual(parseCommand("/codex target"), {
    kind: "command", command: "target", targetSelector: null
  });
  assert.deepEqual(parseCommand("/codex watch 示例任务-监控"), {
    kind: "command", command: "watch", targetSelector: "示例任务-监控"
  });
  assert.deepEqual(parseCommand("/codex queue"), { kind: "command", command: "queue" });
  assert.deepEqual(parseCommand("/codex cancel"), { kind: "command", command: "cancel", requestId: null });
  assert.deepEqual(parseCommand("/codex 当前状态"), {
    kind: "command", command: "send", useBoundTarget: true, instruction: "当前状态"
  });
});

test("does not treat a prefix collision as a command", () => {
  assert.deepEqual(parseCommand("/codexx status"), { kind: "not-command" });
  assert.deepEqual(parseCommand("hello /codex status"), { kind: "not-command" });
});

test("does not treat watermarked controller output as a command", () => {
  assert.deepEqual(parseCommand("【AI生成】\n/codex status"), { kind: "not-command" });
});

test("rejects extra arguments and control characters", () => {
  assert.throws(() => parseCommand("/codex status now"), { code: "COMMAND_INVALID" });
  assert.throws(() => parseCommand("/codex run BAD"), { code: "COMMAND_INVALID" });
  assert.throws(() => parseCommand("/codex help\u0000"), { code: "COMMAND_CONTROL_CHARACTER" });
});

test("counts Unicode code points for limits", () => {
  assert.throws(() => parseCommand(`/codex help${"测".repeat(120)}`), { code: "COMMAND_TOO_LONG" });
});
