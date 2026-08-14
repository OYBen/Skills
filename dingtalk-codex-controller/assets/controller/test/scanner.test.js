import test from "node:test";
import assert from "node:assert/strict";
import { Store } from "../src/store.js";
import { scanOnce } from "../src/scanner.js";

const config = {
  closedWindowDelaySeconds: 10,
  overlapSeconds: 300,
  limits: { pageSize: 100, maxPagesPerScan: 5 },
  channel: {
    conversationId: "conv-1",
    peerUserId: "peer-user",
    peerOpenDingTalkId: "peer-open",
    selfUserId: "self-user",
    selfOpenDingTalkId: "self-open"
  },
  actions: {}
};

function command(id) {
  return {
    openMessageId: id,
    createTime: "2026-08-13T04:59:00.000Z",
    openConversationId: "conv-1",
    senderUserId: "peer-user",
    senderOpenDingTalkId: "peer-open",
    msgType: "text",
    text: { content: "/codex help" }
  };
}

test("overlapping scans deduplicate by message ID", async () => {
  const store = new Store(":memory:");
  const dwsClient = { searchCommands: async () => ({ result: { items: [command("m-1")], hasMore: false } }) };
  try {
    const first = await scanOnce({ config, store, dwsClient }, { now: new Date("2026-08-13T05:00:00.000Z") });
    const second = await scanOnce({ config, store, dwsClient }, { now: new Date("2026-08-13T05:01:00.000Z") });
    assert.equal(first.status, "COMPLETE");
    assert.equal(second.processed[0].disposition, "DUPLICATE");
    assert.equal(store.health().counts.jobs, 1);
  } finally { store.close(); }
});

test("pagination ambiguity sets POLL_GAP_RISK", async () => {
  const store = new Store(":memory:");
  const dwsClient = { searchCommands: async () => ({ result: { items: [], hasMore: true } }) };
  try {
    const result = await scanOnce({ config, store, dwsClient }, { now: new Date("2026-08-13T05:00:00.000Z") });
    assert.equal(result.status, "POLL_GAP_RISK");
    assert.equal(store.health().scans[0].state, "POLL_GAP_RISK");
  } finally { store.close(); }
});

test("long catch-up window fails closed before calling DWS", async () => {
  const store = new Store(":memory:");
  let calls = 0;
  const channelKey = (await import("../src/util.js")).hashIdentifier(config.channel.conversationId);
  store.setScanState(channelKey, "COMPLETE", { closedWindowEnd: "2026-08-13T03:00:00.000Z" });
  try {
    const result = await scanOnce({
      config: { ...config, limits: { ...config.limits, maxCatchUpSeconds: 1800 } },
      store,
      dwsClient: { searchCommands: async () => { calls += 1; return { result: { items: [], hasMore: false } }; } }
    }, { now: new Date("2026-08-13T05:00:00.000Z") });
    assert.equal(result.reason, "CATCH_UP_WINDOW_EXCEEDED");
    assert.equal(calls, 0);
  } finally { store.close(); }
});

test("accepts the nested self-chat shape observed from DWS", async () => {
  const store = new Store(":memory:");
  const selfConfig = {
    ...config,
    mode: "observe",
    channel: {
      kind: "self-chat",
      conversationId: "conv-1",
      peerUserId: "self-user",
      peerOpenDingTalkId: "self-open",
      selfUserId: "self-user",
      selfOpenDingTalkId: "self-open"
    }
  };
  const dwsClient = { searchCommands: async () => ({
    result: {
      conversationMessagesList: [{
        openConversationId: "conv-1",
        messages: [{
          openMessageId: "real-self-message",
          createTime: "2026-08-13 04:59:00",
          senderOpenDingTalkId: "self-open",
          content: "/codex help"
        }]
      }],
      hasMore: false
    }
  }) };
  try {
    const result = await scanOnce({ config: selfConfig, store, dwsClient }, {
      now: new Date("2026-08-13T05:00:00.000Z")
    });
    assert.equal(result.status, "COMPLETE");
    assert.equal(result.fetched, 1);
    assert.equal(result.processed[0].disposition, "OBSERVED");
    assert.equal(store.health().counts.jobs, 1);
  } finally { store.close(); }
});
