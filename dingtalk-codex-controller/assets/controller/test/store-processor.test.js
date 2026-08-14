import test from "node:test";
import assert from "node:assert/strict";
import { Store } from "../src/store.js";
import { processRawMessage } from "../src/processor.js";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";

const config = {
  limits: { maxAcceptedPerFiveMinutes: 5, maxAcceptedPerHour: 20 },
  task: { enrolled: true, threadId: "fixture-thread" },
  channel: {
    kind: "direct",
    conversationId: "conv-1",
    peerUserId: "peer-user",
    peerOpenDingTalkId: "peer-open",
    selfUserId: "self-user",
    selfOpenDingTalkId: "self-open"
  },
  actions: {
    "health-check": { enabled: false, promptSha256: "abc" }
  }
};

function message(id, text = "/codex help", overrides = {}) {
  return {
    openMessageId: id,
    createTime: "2026-08-13T04:00:00.000Z",
    openConversationId: "conv-1",
    senderUserId: "peer-user",
    senderOpenDingTalkId: "peer-open",
    msgType: "text",
    text: { content: text },
    ...overrides
  };
}

test("records an authorized command once in observe mode", () => {
  const store = new Store(":memory:");
  try {
    const first = processRawMessage(message("m-1"), { config, store });
    const second = processRawMessage(message("m-1"), { config, store });
    assert.equal(first.disposition, "OBSERVED");
    assert.equal(second.disposition, "DUPLICATE");
    assert.equal(store.health().counts.jobs, 1);
  } finally { store.close(); }
});

test("never accepts disabled run actions", () => {
  const store = new Store(":memory:");
  try {
    assert.equal(processRawMessage(message("m-2", "/codex run health-check"), { config, store }).disposition, "REJECTED_ACTION_DISABLED");
    assert.equal(store.health().counts.jobs, 0);
  } finally { store.close(); }
});

test("taskless observe rejects run without creating a job", () => {
  const store = new Store(":memory:");
  try {
    const taskless = { ...config, task: { enrolled: false } };
    assert.equal(processRawMessage(message("m-taskless", "/codex run health-check"), { config: taskless, store }).disposition, "REJECTED_TASK_UNENROLLED");
    assert.equal(store.health().counts.jobs, 0);
  } finally { store.close(); }
});

test("identity mismatch cannot create a job", () => {
  const store = new Store(":memory:");
  try {
    const result = processRawMessage(message("m-3", "/codex help", { senderUserId: "other" }), { config, store });
    assert.equal(result.disposition, "REJECTED_IDENTITY");
    assert.equal(store.health().counts.jobs, 0);
  } finally { store.close(); }
});

test("known outbound messages cannot loop back into command processing", () => {
  const store = new Store(":memory:");
  try {
    store.recordOutboundMessage("uuid-1", "m-out");
    const result = processRawMessage(message("m-out"), { config, store });
    assert.equal(result.disposition, "IGNORED_OUTBOUND");
    assert.equal(store.health().counts.jobs, 0);
  } finally { store.close(); }
});

test("known outbound messages remain ignored in self-chat mode", () => {
  const store = new Store(":memory:");
  const selfChatConfig = {
    ...config,
    channel: {
      kind: "self-chat",
      conversationId: "conv-1",
      peerUserId: "self-user",
      peerOpenDingTalkId: "self-open",
      selfUserId: "self-user",
      selfOpenDingTalkId: "self-open"
    }
  };
  try {
    store.recordOutboundMessage("uuid-self", "m-self-out");
    const result = processRawMessage(message("m-self-out", "/codex help", {
      senderUserId: "self-user",
      senderOpenDingTalkId: "self-open"
    }), { config: selfChatConfig, store });
    assert.equal(result.disposition, "IGNORED_OUTBOUND");
    assert.equal(store.health().counts.jobs, 0);
  } finally { store.close(); }
});

test("rate limit rejects commands before a sixth job is created", () => {
  const store = new Store(":memory:");
  try {
    for (let index = 0; index < 5; index += 1) {
      assert.equal(processRawMessage(message(`rate-${index}`), { config, store, now: new Date() }).disposition, "OBSERVED");
    }
    assert.equal(processRawMessage(message("rate-6"), { config, store, now: new Date() }).disposition, "REJECTED_RATE_LIMIT");
    assert.equal(store.health().counts.jobs, 5);
  } finally { store.close(); }
});

test("persists targeted instruction in a restricted file and only its hash in SQLite", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-processor-"));
  const store = new Store(":memory:");
  const active = { ...config, mode: "active", paths: { payloads: directory } };
  try {
    const result = await processRawMessage(message(
      "send-1",
      "/codex send 00000000-0000-0000-0000-000000000011 verify progress"
    ), { config: active, store });
    assert.equal(result.disposition, "OBSERVED");
    const job = store.getJob(result.requestId);
    assert.equal(job.target_thread_id, "00000000-0000-0000-0000-000000000011");
    assert.equal(await readFile(job.instruction_path, "utf8"), "verify progress");
    const serialized = JSON.stringify(job);
    assert.doesNotMatch(serialized, /verify progress/);
    assert.match(job.instruction_sha256, /^[a-f0-9]{64}$/u);
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("bound-target shorthand snapshots both target and watch bindings", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-bound-target-"));
  const store = new Store(":memory:");
  const active = { ...config, mode: "active", paths: { payloads: directory } };
  const targetId = "00000000-0000-0000-0000-000000000012";
  const watchId = "00000000-0000-0000-0000-000000000011";
  try {
    store.setBinding(active.channel.conversationId, { targetThreadId: targetId, watchThreadId: watchId });
    const result = await processRawMessage(message("bound-1", "/codex 查询当前状态"), { config: active, store });
    const job = store.getJob(result.requestId);
    assert.equal(job.target_thread_id, targetId);
    assert.equal(job.watch_thread_id, watchId);
    assert.equal(await readFile(job.instruction_path, "utf8"), "查询当前状态");
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});
