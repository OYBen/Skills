import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { Store } from "../src/store.js";
import { startFixedAction, startTargetInstruction } from "../src/job-runner.js";
import {
  prepareTextDelivery, assertDeliveryNotAutomaticallySendable, resolveEnrolledDeliveryTarget
} from "../src/outbox.js";
import { trustedOpenDingTalkId, trustedUserId } from "../test-support/trusted-fixture.js";

function seedJob(store, state = "ACK_SENT", action = null) {
  const message = {
    messageId: "m-run", conversationId: "conv", senderUserId: "peer",
    senderOpenDingTalkId: "peer-open", createdAt: "2026-08-13T05:00:00.000Z",
    text: action ? `/codex run ${action.alias}` : "/codex status"
  };
  const accepted = store.acceptCommand(
    message,
    action ? { command: "run", actionAlias: action.alias } : { command: "status" },
    action ? { promptSha256: action.promptSha256 } : null
  );
  store.db.prepare("UPDATE jobs SET state = ? WHERE request_id = ?").run(state, accepted.requestId);
  return accepted.requestId;
}

const gates = { runEnabled: true };

async function actionFixture(store) {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-action-"));
  const promptPath = path.join(directory, "action.txt");
  const promptText = "fixed action";
  await writeFile(promptPath, promptText, "utf8");
  const promptSha256 = (await import("../src/util.js")).sha256(promptText);
  const action = { alias: "health-check", enabled: true, promptPath, promptSha256 };
  const config = {
    mode: "active",
    channel: {
      kind: "self-chat",
      peerUserId: trustedUserId,
      peerOpenDingTalkId: trustedOpenDingTalkId,
      selfUserId: trustedUserId,
      selfOpenDingTalkId: trustedOpenDingTalkId
    },
    task: { threadId: "thread", expectedTitle: "Controller Fixture", cwd: "sandbox", permissionProfile: ":read-only" },
    actions: { "health-check": action },
    gates: {
      dwsProtocolVerified: true,
      codexPermissionVerified: true,
      codexReconciliationVerified: true,
      outboundAuthorizationVerified: true
    },
    delivery: { mode: "trusted-self", trustedRecipientName: "欧阳斌" }
  };
  const requestId = seedJob(store, "ACK_SENT", action);
  return { directory, config, requestId };
}

test("records one start attempt and persists the returned turn", async () => {
  const store = new Store(":memory:");
  let calls = 0;
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    const result = await startFixedAction({
      config: fixture.config, gates, store, requestId: fixture.requestId,
      codexClient: {
        listPermissionProfiles: async () => ({ profiles: [{ id: ":read-only", allowed: true }] }),
        readThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "notLoaded" } } }),
        resumeThread: async (_threadId, options) => {
          assert.equal(options.permissionProfile, ":read-only");
          assert.equal(options.approvalPolicy, "never");
          return { thread: { id: "thread", name: "Controller Fixture", status: { type: "idle" } }, cwd: "sandbox", sandbox: { type: "readOnly" } };
        },
        startTurn: async (_threadId, text, options) => { calls += 1; assert.equal(text, "fixed action"); assert.equal(options.approvalPolicy, "never"); return { turn: { id: "turn-1" } }; }
      }
    });
    assert.equal(result.status, "RUNNING");
    assert.equal(calls, 1);
    assert.equal(store.getJob(fixture.requestId).codex_turn_id, "turn-1");
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("ambiguous start becomes START_UNKNOWN and is never retried", async () => {
  const store = new Store(":memory:");
  let calls = 0;
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    const context = {
      config: fixture.config, gates, store, requestId: fixture.requestId,
      codexClient: {
        listPermissionProfiles: async () => ({ profiles: [{ id: ":read-only", allowed: true }] }),
        readThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "notLoaded" } } }),
        resumeThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "idle" } }, cwd: "sandbox", sandbox: { type: "readOnly" } }),
        startTurn: async () => { calls += 1; throw Object.assign(new Error("timeout"), { code: "CODEX_RPC_TIMEOUT" }); }
      }
    };
    assert.equal((await startFixedAction(context)).status, "START_UNKNOWN");
    await assert.rejects(startFixedAction(context), { code: "JOB_STATE" });
    assert.equal(calls, 1);
    assert.equal(store.getJob(fixture.requestId).state, "START_UNKNOWN");
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("run gate blocks before any Codex call", async () => {
  const store = new Store(":memory:");
  let calls = 0;
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    await assert.rejects(startFixedAction({
      config: fixture.config, gates: { runEnabled: false }, store, requestId: fixture.requestId,
      codexClient: { startTurn: async () => { calls += 1; } }
    }), { code: "RUN_GATE_BLOCKED" });
    assert.equal(calls, 0);
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("caller cannot bypass closed configuration gates", async () => {
  const store = new Store(":memory:");
  let calls = 0;
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    fixture.config.gates.outboundAuthorizationVerified = false;
    await assert.rejects(startFixedAction({
      config: fixture.config, gates: { runEnabled: true }, store, requestId: fixture.requestId,
      codexClient: { startTurn: async () => { calls += 1; } }
    }), { code: "RUN_GATE_BLOCKED" });
    assert.equal(calls, 0);
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("refuses a mismatched or active dedicated task before turn start", async () => {
  const store = new Store(":memory:");
  let calls = 0;
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    await assert.rejects(startFixedAction({
      config: fixture.config, gates, store, requestId: fixture.requestId,
      codexClient: {
        listPermissionProfiles: async () => ({ profiles: [{ id: ":read-only", allowed: true }] }),
        readThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "active" } } }),
        startTurn: async () => { calls += 1; }
      }
    }), { code: "THREAD_NOT_IDLE" });
    assert.equal(calls, 0);
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("requires resume to report the exact cwd", async () => {
  const store = new Store(":memory:");
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    await assert.rejects(startFixedAction({
      config: fixture.config, gates, store, requestId: fixture.requestId,
      codexClient: {
        listPermissionProfiles: async () => ({ profiles: [{ id: ":read-only", allowed: true }] }),
        readThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "notLoaded" } } }),
        resumeThread: async () => ({
          thread: { id: "thread", name: "Controller Fixture", status: { type: "idle" } },
          sandbox: { type: "readOnly" }
        })
      }
    }), { code: "THREAD_CWD_MISMATCH" });
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("lease loss after turn start leaves an in-flight state for crash recovery", async () => {
  const store = new Store(":memory:");
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    let held = true;
    await assert.rejects(startFixedAction({
      config: fixture.config, gates, store, requestId: fixture.requestId,
      assertLease: () => { if (!held) throw Object.assign(new Error("lost"), { code: "CONTROLLER_LEASE_LOST" }); },
      leaseTransaction: (callback) => callback(),
      codexClient: {
        listPermissionProfiles: async () => ({ profiles: [{ id: ":read-only", allowed: true }] }),
        readThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "notLoaded" } } }),
        resumeThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "idle" } }, cwd: "sandbox", sandbox: { type: "readOnly" } }),
        startTurn: async () => { held = false; return { turn: { id: "turn-lost" } }; }
      }
    }), { code: "CONTROLLER_LEASE_LOST" });
    assert.equal(store.getJob(fixture.requestId).state, "START_CALL_IN_FLIGHT");
    assert.deepEqual(store.recoverInFlightStates(), { jobs: 1, deliveries: 0 });
    assert.equal(store.getJob(fixture.requestId).state, "START_UNKNOWN");
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("never reports RUNNING when accepted turn state cannot be persisted", async () => {
  const store = new Store(":memory:");
  let directory;
  try {
    const fixture = await actionFixture(store);
    ({ directory } = fixture);
    const originalTransition = store.transitionJob.bind(store);
    store.transitionJob = (requestId, expected, next, values) => {
      if (expected === "START_CALL_IN_FLIGHT" && next === "RUNNING") return false;
      return originalTransition(requestId, expected, next, values);
    };
    const result = await startFixedAction({
      config: fixture.config, gates, store, requestId: fixture.requestId,
      codexClient: {
        listPermissionProfiles: async () => ({ profiles: [{ id: ":read-only", allowed: true }] }),
        readThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "notLoaded" } } }),
        resumeThread: async () => ({ thread: { id: "thread", name: "Controller Fixture", status: { type: "idle" } }, cwd: "sandbox", sandbox: { type: "readOnly" } }),
        startTurn: async () => ({ turn: { id: "turn-accepted" } })
      }
    });
    assert.equal(result.status, "START_UNKNOWN");
    assert.equal(store.getJob(fixture.requestId).state, "START_UNKNOWN");
  } finally { store.close(); if (directory) await rm(directory, { recursive: true, force: true }); }
});

test("targeted instruction uses the live Desktop owner and starts exactly one visible turn", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-instruction-"));
  const instructionPath = path.join(directory, "instruction.txt");
  const instruction = "inspect current status";
  await writeFile(instructionPath, instruction, "utf8");
  const store = new Store(":memory:");
  let starts = 0;
  try {
    const fixture = await actionFixture(store);
    await rm(fixture.directory, { recursive: true, force: true });
    const requestId = fixture.requestId;
    const targetId = "00000000-0000-0000-0000-000000000011";
    store.db.prepare(`UPDATE jobs SET command='send', action_alias=NULL, prompt_sha256=NULL,
      target_thread_id=?, instruction_path=?, instruction_sha256=? WHERE request_id=?`)
      .run(targetId, instructionPath, (await import("../src/util.js")).sha256(instruction), requestId);
    const target = { id: targetId, name: "Target", cwd: directory, status: { type: "idle" }, archived: false };
    const result = await startTargetInstruction({
      config: fixture.config, gates, store, requestId,
      threadDirectory: {
        listThreads: async ({ archived }) => ({ data: archived ? [] : [target], nextCursor: null }),
      },
      desktopClient: {
        findThreadOwner: async () => "desktop-owner",
        startThreadTurn: async (_id, text, options) => {
          starts += 1;
          assert.equal(text, instruction);
          assert.equal(options.ownerClientId, "desktop-owner");
          return { turn: { id: "target-turn" } };
        }
      }
    });
    assert.equal(result.status, "RUNNING");
    assert.equal(starts, 1);
    assert.equal(store.getJob(requestId).target_thread_id, targetId);
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("targeted instruction rejects active or archived tasks before turn start", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-instruction-reject-"));
  const instructionPath = path.join(directory, "instruction.txt");
  await writeFile(instructionPath, "do work", "utf8");
  const store = new Store(":memory:");
  let starts = 0;
  try {
    const fixture = await actionFixture(store);
    await rm(fixture.directory, { recursive: true, force: true });
    const targetId = "00000000-0000-0000-0000-000000000011";
    store.db.prepare(`UPDATE jobs SET command='send', action_alias=NULL, target_thread_id=?,
      instruction_path=?, instruction_sha256=? WHERE request_id=?`)
      .run(targetId, instructionPath, (await import("../src/util.js")).sha256("do work"), fixture.requestId);
    await assert.rejects(startTargetInstruction({
      config: fixture.config, gates, store, requestId: fixture.requestId,
      threadDirectory: {
        listThreads: async ({ archived }) => ({
          data: archived ? [] : [{ id: targetId, cwd: directory, status: { type: "active" } }], nextCursor: null
        }),
      },
      desktopClient: {
        findThreadOwner: async () => "desktop-owner",
        startThreadTurn: async () => { starts += 1; }
      }
    }), { code: "THREAD_ACTIVE" });
    assert.equal(starts, 0);
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("targeted instruction requires a live Codex Desktop owner", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-instruction-owner-"));
  const instructionPath = path.join(directory, "instruction.txt");
  await writeFile(instructionPath, "do visible work", "utf8");
  const store = new Store(":memory:");
  let starts = 0;
  try {
    const fixture = await actionFixture(store);
    await rm(fixture.directory, { recursive: true, force: true });
    const targetId = "00000000-0000-0000-0000-000000000011";
    store.db.prepare(`UPDATE jobs SET command='send', action_alias=NULL, target_thread_id=?,
      instruction_path=?, instruction_sha256=? WHERE request_id=?`)
      .run(targetId, instructionPath, (await import("../src/util.js")).sha256("do visible work"), fixture.requestId);
    await assert.rejects(startTargetInstruction({
      config: fixture.config, gates, store, requestId: fixture.requestId,
      threadDirectory: {
        listThreads: async ({ archived }) => ({
          data: archived ? [] : [{ id: targetId, cwd: directory, status: { type: "idle" }, archived: false }],
          nextCursor: null
        })
      },
      desktopClient: {
        findThreadOwner: async () => null,
        startThreadTurn: async () => { starts += 1; }
      }
    }), { code: "DESKTOP_THREAD_OWNER_UNAVAILABLE" });
    assert.equal(starts, 0);
    assert.equal(store.getJob(fixture.requestId).state, "ACK_SENT");
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("prepares a watermarked immutable outbox item without sending", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-outbox-"));
  const store = new Store(":memory:");
  try {
    const requestId = seedJob(store, "OBSERVED");
    const localConfig = { delivery: { mode: "local-approval" }, paths: { payloads: directory } };
    const prepared = await prepareTextDelivery({
      config: localConfig,
      store,
      requestId,
      sourceText: "Observed command; no action executed.",
      target: { conversationId: "conv", referenceMessageId: "m-run", referenceSenderOpenDingTalkId: "peer-open" }
    });
    assert.equal(prepared.state, "AWAITING_SEND_APPROVAL");
    const delivery = store.getDelivery(prepared.deliveryId);
    assert.equal(delivery.attempt_count, 0);
    assert.equal(assertDeliveryNotAutomaticallySendable(delivery), true);
    assert.deepEqual(resolveEnrolledDeliveryTarget(delivery, store.getJob(requestId), {
      channel: { conversationId: "conv", peerOpenDingTalkId: "peer-open" }
    }), {
      conversationId: "conv", referenceMessageId: "m-run", referenceSenderOpenDingTalkId: "peer-open"
    });
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});
