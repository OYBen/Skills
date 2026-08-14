import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { Store } from "../src/store.js";
import { acquireControllerLease } from "../src/lease.js";
import { runControllerService, runObserveService } from "../src/service.js";
import { trustedOpenDingTalkId, trustedUserId } from "../test-support/trusted-fixture.js";

test("database lease rejects a second instance and releases cleanly", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-lock-"));
  const databasePath = path.join(directory, "controller.db");
  const firstStore = new Store(databasePath);
  const secondStore = new Store(databasePath);
  try {
    const first = acquireControllerLease(firstStore, { ownerId: "owner-1", heartbeatMilliseconds: 60_000 });
    assert.throws(() => acquireControllerLease(secondStore, { ownerId: "owner-2" }), { code: "INSTANCE_ALREADY_RUNNING" });
    first.release();
    const second = acquireControllerLease(secondStore, { ownerId: "owner-2", heartbeatMilliseconds: 60_000 });
    second.release();
  } finally {
    firstStore.close();
    secondStore.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("expired database lease is reclaimed atomically", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-stale-lease-"));
  const databasePath = path.join(directory, "controller.db");
  let now = new Date("2026-08-13T05:00:00.000Z");
  const clock = () => now;
  const firstStore = new Store(databasePath, { clock });
  const secondStore = new Store(databasePath, { clock });
  try {
    const first = acquireControllerLease(firstStore, { ownerId: "owner-1", ttlSeconds: 10, heartbeatMilliseconds: 60_000 });
    now = new Date("2026-08-13T05:00:11.000Z");
    const second = acquireControllerLease(secondStore, { ownerId: "owner-2", ttlSeconds: 10, heartbeatMilliseconds: 60_000 });
    assert.throws(() => first.assertHeld(), { code: "CONTROLLER_LEASE_LOST" });
    first.release();
    second.release();
  } finally {
    firstStore.close();
    secondStore.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("lease fencing validates ownership in the same write transaction", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-lease-fence-"));
  const databasePath = path.join(directory, "controller.db");
  let now = new Date("2026-08-13T05:00:00.000Z");
  const store = new Store(databasePath, { clock: () => now });
  try {
    const oldLease = acquireControllerLease(store, { ownerId: "owner-old", ttlSeconds: 10, heartbeatMilliseconds: 60_000 });
    oldLease.transaction(() => store.audit("FENCED_WRITE", { owner: "old" }));
    now = new Date("2026-08-13T05:00:11.000Z");
    assert.throws(
      () => oldLease.transaction(() => store.audit("MUST_NOT_WRITE", { owner: "old" })),
      { code: "CONTROLLER_LEASE_LOST" }
    );
    assert.equal(store.health().counts.audit_events, 1);
    oldLease.release();
  } finally {
    store.close();
    await rm(directory, { recursive: true, force: true });
  }
});

test("observe service runs one scan without sends or turns", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-service-"));
  const configPath = path.join(directory, "config.json");
  const cwd = path.resolve("sandbox");
  const config = {
    schemaVersion: 1,
    mode: "observe",
    pollIntervalSeconds: 60,
    closedWindowDelaySeconds: 10,
    overlapSeconds: 300,
    channel: {
      kind: "direct",
      conversationId: "conv", peerUserId: "peer", peerOpenDingTalkId: "peer-open",
      selfUserId: "self", selfOpenDingTalkId: "self-open"
    },
    task: { threadId: "thread", expectedTitle: "Fixture", cwd, permissionProfile: ":read-only" },
    actions: {},
    gates: {
      dwsProtocolVerified: false, codexPermissionVerified: false,
      codexReconciliationVerified: false, outboundAuthorizationVerified: false
    },
    delivery: { mode: "disabled" },
    limits: { pageSize: 10, maxPagesPerScan: 2, outboxRetryWindowSeconds: 60 },
    paths: { database: "data/service.db", payloads: "data/payloads" }
  };
  await import("node:fs/promises").then(({ writeFile }) => writeFile(configPath, JSON.stringify(config), "utf8"));
  const fake = {
    getSelf: async () => ({ result: [{ orgEmployeeModel: { orgUserName: "Fixture User", userId: "self" } }] }),
    searchPersonByName: async () => ({ result: [{ meta: { name: "Fixture User" }, userId: "self", openDingTalkId: "self-open" }] }),
    searchCommands: async () => ({ result: { items: [], hasMore: false } })
  };
  try {
    const result = await runObserveService({ configPath, dwsClient: fake, once: true });
    assert.equal(result.scans, 1);
    assert.equal(result.health.counts.jobs, 0);
    assert.equal(result.health.counts.deliveries, 0);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("taskless self-chat observe runs without Codex or delivery", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-taskless-self-"));
  const configPath = path.join(directory, "config.json");
  const config = {
    schemaVersion: 1,
    mode: "observe",
    pollIntervalSeconds: 60,
    closedWindowDelaySeconds: 10,
    overlapSeconds: 300,
    channel: {
      kind: "self-chat",
      conversationId: "conv-self",
      peerUserId: "self",
      peerOpenDingTalkId: "self-open",
      selfUserId: "self",
      selfOpenDingTalkId: "self-open"
    },
    task: { enrolled: false },
    actions: {},
    gates: {
      dwsProtocolVerified: false,
      codexPermissionVerified: false,
      codexReconciliationVerified: false,
      outboundAuthorizationVerified: false
    },
    delivery: { mode: "disabled" },
    limits: { pageSize: 10, maxPagesPerScan: 2, outboxRetryWindowSeconds: 60 },
    paths: { database: "data/service.db", payloads: "data/payloads" }
  };
  await import("node:fs/promises").then(({ writeFile }) => writeFile(configPath, JSON.stringify(config), "utf8"));
  const fake = {
    getSelf: async () => ({ result: [{ orgEmployeeModel: { orgUserName: "Fixture User", userId: "self" } }] }),
    searchPersonByName: async () => ({ result: [{ meta: { name: "Fixture User" }, userId: "self", openDingTalkId: "self-open" }] }),
    searchCommands: async () => ({ result: { hasMore: false, nextCursor: "" } })
  };
  try {
    const result = await runObserveService({ configPath, dwsClient: fake, once: true });
    assert.equal(result.scans, 1);
    assert.equal(result.health.counts.jobs, 0);
    assert.equal(result.health.counts.deliveries, 0);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("active idle startup does not start an independent App Server", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-active-idle-"));
  const configDirectory = path.join(directory, "config");
  const actionDirectory = path.join(configDirectory, "actions");
  const configPath = path.join(configDirectory, "config.json");
  await mkdir(actionDirectory, { recursive: true });
  const prompt = await readFile(path.resolve("config/actions/health-check.txt"), "utf8");
  await writeFile(path.join(actionDirectory, "health-check.txt"), prompt, "utf8");
  const config = {
    schemaVersion: 1,
    mode: "active",
    pollIntervalSeconds: 60,
    closedWindowDelaySeconds: 10,
    overlapSeconds: 300,
    channel: {
      kind: "self-chat", conversationId: "conv",
      peerUserId: trustedUserId, peerOpenDingTalkId: trustedOpenDingTalkId,
      selfUserId: trustedUserId, selfOpenDingTalkId: trustedOpenDingTalkId
    },
    task: {
      threadId: "thread", expectedTitle: "Fixture", cwd: directory,
      permissionProfile: ":read-only"
    },
    actions: {
      "health-check": {
        promptFile: "config/actions/health-check.txt",
        promptSha256: "84656e10ba7dde5faacc519247fb149c63b7cf661d8a4a6408691b49d8be0e2d",
        enabled: true
      }
    },
    gates: {
      dwsProtocolVerified: true, codexPermissionVerified: true,
      codexReconciliationVerified: true, outboundAuthorizationVerified: true
    },
    delivery: { mode: "trusted-self", trustedRecipientName: "欧阳斌" },
    limits: { pageSize: 10, maxPagesPerScan: 2, outboxRetryWindowSeconds: 60 },
    paths: { database: "data/service.db", payloads: "data/payloads" }
  };
  await writeFile(configPath, JSON.stringify(config), "utf8");
  const dwsClient = {
    getSelf: async () => ({ result: [{ orgEmployeeModel: { orgUserName: "欧阳斌", userId: trustedUserId } }] }),
    searchPersonByName: async () => ({ result: [{
      meta: { name: "欧阳斌" }, userId: trustedUserId, openDingTalkId: trustedOpenDingTalkId
    }] }),
    searchCommands: async () => ({ result: { items: [], hasMore: false } })
  };
  let starts = 0;
  const codexClient = {
    start: async () => { starts += 1; },
    stop: async () => {}
  };
  try {
    const result = await runControllerService({
      configPath, dwsClient, codexClient,
      desktopClient: { stop: async () => {} },
      once: true
    });
    assert.equal(result.scans, 1);
    assert.equal(starts, 0);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
