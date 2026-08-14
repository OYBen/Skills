import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { Store } from "../src/store.js";
import { advanceController } from "../src/controller-workflow.js";
import { prepareTextDelivery } from "../src/outbox.js";
import { sendTrustedDelivery } from "../src/delivery-worker.js";
import { trustedOpenDingTalkId, trustedUserId } from "../test-support/trusted-fixture.js";

function config(directory) {
  return {
    mode: "active",
    channel: {
      kind: "self-chat", conversationId: "conv",
      peerUserId: trustedUserId, peerOpenDingTalkId: trustedOpenDingTalkId,
      selfUserId: trustedUserId, selfOpenDingTalkId: trustedOpenDingTalkId
    },
    task: {
      enrolled: true, threadId: "thread", expectedTitle: "DingTalk Controller",
      cwd: directory, permissionProfile: ":read-only"
    },
    actions: {},
    gates: {
      dwsProtocolVerified: true, codexPermissionVerified: true,
      codexReconciliationVerified: true, outboundAuthorizationVerified: true
    },
    delivery: { mode: "trusted-self", trustedRecipientName: "欧阳斌" },
    paths: { payloads: path.join(directory, "payloads") }
  };
}

function message(id, text) {
  return {
    messageId: id, conversationId: "conv", senderUserId: "self",
    senderOpenDingTalkId: trustedOpenDingTalkId, createdAt: "2026-08-13T08:00:00.000Z", text
  };
}

function trustedDws(overrides = {}) {
  return {
    searchPersonByName: async () => ({ result: [{ meta: { name: "欧阳斌" }, userId: trustedUserId, openDingTalkId: trustedOpenDingTalkId }] }),
    replyMessage: async () => ({ success: true, result: { openMessageId: "sent-message" } }),
    ...overrides
  };
}

test("active local help completes and sends one watermarked reply", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-active-help-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const accepted = store.acceptCommand(message("help-message", "/codex help"), { command: "help" }, null, "PENDING");
    const events = await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), codexClient: {} });
    assert.equal(store.getJob(accepted.requestId).state, "DELIVERED");
    const delivery = store.getDeliveryForRequest(accepted.requestId, "result");
    assert.equal(delivery.state, "SENT");
    assert.match(await readFile(delivery.payload_path, "utf8"), /^【AI生成】\n/u);
    assert.ok(events.some((event) => event.status === "SENT"));
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("trusted delivery rechecks both IDs and falls back to approval", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-trusted-fail-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const accepted = store.acceptCommand(message("status-message", "/codex status"), { command: "status" }, null, "COMPLETED");
    const prepared = await prepareTextDelivery({
      config: cfg, store, requestId: accepted.requestId, sourceText: "status", kind: "result",
      target: { conversationId: "conv", referenceMessageId: "status-message", referenceSenderOpenDingTalkId: trustedOpenDingTalkId }
    });
    let sends = 0;
    const result = await sendTrustedDelivery({
      config: cfg, store, deliveryId: prepared.deliveryId,
      dwsClient: trustedDws({
        searchPersonByName: async () => ({ result: [{ meta: { name: "欧阳斌" }, userId: "other", openDingTalkId: trustedOpenDingTalkId }] }),
        replyMessage: async () => { sends += 1; return { success: true }; }
      })
    });
    assert.equal(result.status, "AWAITING_SEND_APPROVAL");
    assert.equal(sends, 0);
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("delivery retries once with the same UUID", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-trusted-retry-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const accepted = store.acceptCommand(message("retry-message", "/codex status"), { command: "status" }, null, "COMPLETED");
    const prepared = await prepareTextDelivery({
      config: cfg, store, requestId: accepted.requestId, sourceText: "status", kind: "result",
      target: { conversationId: "conv", referenceMessageId: "retry-message", referenceSenderOpenDingTalkId: trustedOpenDingTalkId }
    });
    const uuids = [];
    let calls = 0;
    const result = await sendTrustedDelivery({
      config: cfg, store, deliveryId: prepared.deliveryId,
      dwsClient: trustedDws({ replyMessage: async (request) => {
        uuids.push(request.uuid); calls += 1;
        if (calls === 1) throw Object.assign(new Error("temporary"), { code: "PROCESS_TIMEOUT" });
        return { success: true, result: { openMessageId: "sent-after-retry" } };
      } })
    });
    assert.equal(result.status, "SENT");
    assert.equal(uuids.length, 2);
    assert.equal(uuids[0], uuids[1]);
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("explicit DWS rejection is not retried", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-no-auth-retry-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const accepted = store.acceptCommand(message("denied-message", "/codex status"), { command: "status" }, null, "COMPLETED");
    const prepared = await prepareTextDelivery({
      config: cfg, store, requestId: accepted.requestId, sourceText: "status", kind: "result",
      target: { conversationId: "conv", referenceMessageId: "denied-message", referenceSenderOpenDingTalkId: trustedOpenDingTalkId }
    });
    let calls = 0;
    const result = await sendTrustedDelivery({
      config: cfg, store, deliveryId: prepared.deliveryId,
      dwsClient: trustedDws({ replyMessage: async () => {
        calls += 1;
        throw Object.assign(new Error("denied"), { code: "DWS_REMOTE_FAILED" });
      } })
    });
    assert.equal(result.status, "SEND_FAILED");
    assert.equal(calls, 1);
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("lease loss after DingTalk reply leaves delivery unknown for recovery", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-delivery-lease-loss-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const accepted = store.acceptCommand(message("lease-message", "/codex status"), { command: "status" }, null, "COMPLETED");
    const prepared = await prepareTextDelivery({
      config: cfg, store, requestId: accepted.requestId, sourceText: "status", kind: "result",
      target: { conversationId: "conv", referenceMessageId: "lease-message", referenceSenderOpenDingTalkId: trustedOpenDingTalkId }
    });
    let held = true;
    await assert.rejects(sendTrustedDelivery({
      config: cfg,
      store,
      deliveryId: prepared.deliveryId,
      assertLease: () => { if (!held) throw Object.assign(new Error("lost"), { code: "CONTROLLER_LEASE_LOST" }); },
      leaseTransaction: (callback) => callback(),
      dwsClient: trustedDws({ replyMessage: async () => {
        held = false;
        return { success: true, result: { openMessageId: "sent-before-loss" } };
      } })
    }), { code: "CONTROLLER_LEASE_LOST" });
    assert.equal(store.getDelivery(prepared.deliveryId).state, "SEND_CALL_IN_FLIGHT");
    assert.deepEqual(store.recoverInFlightStates(), { jobs: 0, deliveries: 1 });
    assert.equal(store.getDelivery(prepared.deliveryId).state, "DELIVERY_UNKNOWN");
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("failed job notification reaches a terminal notified state", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-failed-notified-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const accepted = store.acceptCommand(message("failed-message", "/codex run health-check"), {
      command: "run", actionAlias: "health-check"
    }, { promptSha256: "fixture" }, "FAILED");
    store.db.prepare("UPDATE jobs SET error_code = 'TURN_FAILED' WHERE request_id = ?").run(accepted.requestId);
    await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), codexClient: {} });
    assert.equal(store.getJob(accepted.requestId).state, "FAILED_NOTIFIED");
    const deliveries = store.listDeliveriesByStates(["SENT"]);
    assert.equal(deliveries.length, 1);
    await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), codexClient: {} });
    assert.equal(store.listDeliveriesByStates(["SENT"]).length, 1);
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("over-limit result is replaced by a short local-review notice", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-long-result-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const accepted = store.acceptCommand(message("long-message", "/codex status"), { command: "status" }, null, "COMPLETED");
    const resultPath = path.join(directory, "long-result.txt");
    const longText = "x".repeat(600);
    const { sha256 } = await import("../src/util.js");
    await writeFile(resultPath, longText, "utf8");
    store.db.prepare("UPDATE jobs SET result_path = ?, result_sha256 = ? WHERE request_id = ?")
      .run(resultPath, sha256(longText), accepted.requestId);
    await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), codexClient: {} });
    const delivery = store.getDeliveryForRequest(accepted.requestId, "result");
    const deliveredText = await readFile(delivery.payload_path, "utf8");
    assert.ok(Array.from(deliveredText).length <= 500);
    assert.match(deliveredText, /结果超过 500 字符/u);
    assert.equal(store.getJob(accepted.requestId).state, "DELIVERED");
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("fixed Codex turn is reconciled by exact turn ID", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-active-run-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  const promptText = "Report healthy in under 100 characters.";
  const promptPath = path.join(directory, "health.txt");
  const rolloutPath = path.join(directory, "rollout.jsonl");
  await writeFile(promptPath, promptText, "utf8");
  await writeFile(rolloutPath, [
    JSON.stringify({ timestamp: "2026-08-13T05:00:00Z", type: "event_msg", payload: { type: "task_started", turn_id: "turn-1" } }),
    JSON.stringify({ timestamp: "2026-08-13T05:00:01Z", type: "event_msg", payload: { type: "task_complete", turn_id: "turn-1", last_agent_message: "Healthy." } })
  ].join("\n"), "utf8");
  const { sha256 } = await import("../src/util.js");
  cfg.actions.health = { alias: "health", enabled: true, promptPath, promptSha256: sha256(promptText) };
  try {
    const accepted = store.acceptCommand(message("run-message", "/codex run health"), { command: "run", actionAlias: "health" }, cfg.actions.health, "ACK_SENT");
    const codexClient = {
      listPermissionProfiles: async () => ({ data: [{ id: ":read-only", allowed: true }] }),
      readThread: async () => ({ thread: { id: "thread", name: "DingTalk Controller", status: { type: "notLoaded" } } }),
      resumeThread: async () => ({ thread: { id: "thread", name: "DingTalk Controller", status: { type: "idle" } }, cwd: directory, sandbox: { type: "readOnly" } }),
      startTurn: async () => ({ turn: { id: "turn-1" } })
    };
    const threadDirectory = {
      listThreads: async ({ archived }) => ({
        data: archived ? [] : [{ id: "thread", name: "DingTalk Controller", cwd: directory, status: { type: "idle" }, rolloutPath }],
        nextCursor: null
      })
    };
    await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), codexClient, threadDirectory });
    assert.equal(store.getJob(accepted.requestId).state, "DELIVERED");
  } finally { store.close(); await rm(directory, { recursive: true, force: true }); }
});

test("active target queues once, then starts and pushes completion after becoming idle", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-active-queue-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  const targetId = "00000000-0000-0000-0000-000000000011";
  const watchId = "00000000-0000-0000-0000-000000000012";
  const instruction = "查询当前状态";
  const instructionPath = path.join(directory, "instruction.txt");
  const rolloutPath = path.join(directory, "rollout.jsonl");
  const { sha256 } = await import("../src/util.js");
  await writeFile(instructionPath, instruction, "utf8");
  await writeFile(rolloutPath, [
    JSON.stringify({ timestamp: "2026-08-14T01:00:00Z", type: "event_msg", payload: { type: "task_started", turn_id: "queued-turn" } }),
    JSON.stringify({ timestamp: "2026-08-14T01:00:01Z", type: "event_msg", payload: { type: "task_complete", turn_id: "queued-turn", last_agent_message: "状态正常。" } })
  ].join("\n"), "utf8");
  let targetStatus = "active";
  let starts = 0;
  const threadDirectory = {
    listThreads: async ({ archived }) => ({
      data: archived ? [] : [{
        id: targetId, name: "示例任务-监控", archived: false,
        status: { type: targetStatus }, rolloutPath
      }],
      nextCursor: null
    })
  };
  const desktopClient = {
    findThreadOwner: async () => "desktop-owner",
    startThreadTurn: async (_threadId, text) => {
      starts += 1;
      assert.match(text, new RegExp(watchId, "u"));
      assert.match(text, /用户指令：查询当前状态/u);
      return { turn: { id: "queued-turn" } };
    }
  };
  try {
    const accepted = store.acceptCommand(message("queued-message", `/codex send ${targetId} ${instruction}`), {
      command: "send", targetThreadId: targetId, watchThreadId: watchId
    }, null, "PENDING", { instructionPath, instructionSha256: sha256(instruction) });

    await advanceController({
      config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(),
      desktopClient, threadDirectory
    });
    assert.equal(store.getJob(accepted.requestId).state, "QUEUED");
    assert.equal(starts, 0);
    assert.equal(store.getDeliveryForRequest(accepted.requestId, "queued").state, "SENT");
    assert.equal(store.getDeliveryForRequest(accepted.requestId, "ack"), null);

    targetStatus = "idle";
    await advanceController({
      config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(),
      desktopClient, threadDirectory
    });
    assert.equal(starts, 1);
    assert.equal(store.getJob(accepted.requestId).state, "DELIVERED");
    assert.equal(store.getDeliveryForRequest(accepted.requestId, "ack").state, "SENT");
    assert.equal(store.getDeliveryForRequest(accepted.requestId, "result").state, "SENT");
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("target preflight failure sends no acceptance acknowledgement", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-preflight-failure-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  const instruction = "查询状态";
  const instructionPath = path.join(directory, "instruction.txt");
  const { sha256 } = await import("../src/util.js");
  await writeFile(instructionPath, instruction, "utf8");
  try {
    const accepted = store.acceptCommand(message("missing-target", "/codex send 不存在 查询状态"), {
      command: "send", targetSelector: "不存在"
    }, null, "PENDING", { instructionPath, instructionSha256: sha256(instruction) });
    await advanceController({
      config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(),
      desktopClient: { findThreadOwner: async () => null },
      threadDirectory: { listThreads: async () => ({ data: [], nextCursor: null }) }
    });
    assert.equal(store.getJob(accepted.requestId).state, "FAILED_NOTIFIED");
    assert.equal(store.getDeliveryForRequest(accepted.requestId, "ack"), null);
    assert.equal(store.getDeliveryForRequest(accepted.requestId, "result").state, "SENT");
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("target binding and thread list persist deterministic routing choices", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-bind-list-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  const targetId = "00000000-0000-0000-0000-000000000012";
  const threadDirectory = {
    listThreads: async ({ archived }) => ({
      data: archived ? [] : [{ id: targetId, name: "示例任务-执行", archived: false, status: { type: "idle" } }],
      nextCursor: null
    })
  };
  const desktopClient = { findThreadOwner: async () => "desktop-owner" };
  try {
    const bind = store.acceptCommand(message("bind-target", "/codex target 示例任务-执行"), {
      command: "target", targetSelector: "示例任务-执行"
    }, null, "PENDING");
    await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), desktopClient, threadDirectory });
    assert.equal(store.getJob(bind.requestId).state, "DELIVERED");
    assert.equal(store.getBinding(cfg.channel.conversationId).target_thread_id, targetId);

    const listing = store.acceptCommand(message("list-targets", "/codex threads"), {
      command: "threads", page: 1
    }, null, "PENDING");
    await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), desktopClient, threadDirectory });
    assert.equal(store.getJob(listing.requestId).state, "DELIVERED");
    assert.equal(store.getThreadSelection(cfg.channel.conversationId, 1), targetId);
    const delivery = store.getDeliveryForRequest(listing.requestId, "result");
    assert.match(await readFile(delivery.payload_path, "utf8"), /空闲，可立即发送/u);
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("idle target without a Desktop owner waits in queue instead of failing", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-owner-queue-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  const targetId = "00000000-0000-0000-0000-000000000012";
  const instruction = "查询状态";
  const instructionPath = path.join(directory, "instruction.txt");
  const { sha256 } = await import("../src/util.js");
  await writeFile(instructionPath, instruction, "utf8");
  try {
    const accepted = store.acceptCommand(message("owner-queue", `/codex send ${targetId} ${instruction}`), {
      command: "send", targetThreadId: targetId
    }, null, "PENDING", { instructionPath, instructionSha256: sha256(instruction) });
    await advanceController({
      config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(),
      desktopClient: { findThreadOwner: async () => null },
      threadDirectory: { listThreads: async ({ archived }) => ({
        data: archived ? [] : [{ id: targetId, name: "示例任务-执行", archived: false, status: { type: "idle" } }],
        nextCursor: null
      }) }
    });
    const job = store.getJob(accepted.requestId);
    assert.equal(job.state, "QUEUED");
    assert.equal(job.queue_reason, "DESKTOP_THREAD_OWNER_UNAVAILABLE");
    assert.equal(store.getDeliveryForRequest(accepted.requestId, "ack"), null);
    assert.match(await readFile(store.getDeliveryForRequest(accepted.requestId, "queued").payload_path, "utf8"), /打开后自动发送/u);
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("cancel command closes the selected queued request", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-cancel-queue-"));
  const store = new Store(":memory:");
  const cfg = config(directory);
  try {
    const queued = store.acceptCommand(message("queued-for-cancel", "/codex query"), {
      command: "send", targetThreadId: "00000000-0000-0000-0000-000000000012"
    }, null, "QUEUED");
    const cancel = store.acceptCommand(message("cancel-command", `/codex cancel ${queued.requestId}`), {
      command: "cancel", requestId: queued.requestId
    }, null, "PENDING");
    await advanceController({ config: cfg, gates: { runEnabled: true }, store, dwsClient: trustedDws(), threadDirectory: { listThreads: async () => ({ data: [], nextCursor: null }) } });
    assert.equal(store.getJob(queued.requestId).state, "CANCELED");
    assert.equal(store.getJob(cancel.requestId).state, "DELIVERED");
    assert.match(await readFile(store.getDeliveryForRequest(cancel.requestId, "result").payload_path, "utf8"), /已取消排队请求/u);
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});
