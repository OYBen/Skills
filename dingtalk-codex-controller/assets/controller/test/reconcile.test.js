import test from "node:test";
import assert from "node:assert/strict";
import { Store } from "../src/store.js";
import { reconcileUnknownStart, summarizeThreadForReconciliation } from "../src/reconcile.js";

test("summarizes turn identities without returning content", () => {
  const result = summarizeThreadForReconciliation({ thread: {
    id: "thread-1", status: { type: "notLoaded" },
    turns: [{ id: "turn-1", status: "completed", startedAt: "2026-08-13T05:00:00Z", items: [{ text: "secret" }] }]
  } }, "thread-1");
  assert.equal(result.turns[0].id, "turn-1");
  assert.equal(result.contentOmitted, true);
  assert.equal(JSON.stringify(result).includes("secret"), false);
});

test("reconciliation reports candidates but never auto-adopts", async () => {
  const clock = () => new Date("2026-08-13T05:00:00Z");
  const store = new Store(":memory:", { clock });
  try {
    const message = {
      messageId: "m-unknown", conversationId: "conv", senderUserId: "peer",
      senderOpenDingTalkId: "peer-open", createdAt: clock().toISOString(), text: "/codex run health-check"
    };
    const accepted = store.acceptCommand(
      message,
      { command: "run", actionAlias: "health-check" },
      { promptSha256: "digest" },
      "START_UNKNOWN"
    );
    store.db.prepare("UPDATE jobs SET start_attempted_at = ? WHERE request_id = ?")
      .run("2026-08-13T05:00:00Z", accepted.requestId);
    const result = await reconcileUnknownStart({
      store,
      requestId: accepted.requestId,
      threadId: "thread-1",
      codexClient: { readThread: async () => ({ thread: {
        id: "thread-1",
        turns: [{ id: "turn-candidate", status: "completed", startedAt: "2026-08-13T05:00:10Z" }]
      } }) }
    });
    assert.equal(result.status, "SINGLE_TIME_CANDIDATE");
    assert.equal(result.automaticAdoptionAllowed, false);
    assert.equal(store.getJob(accepted.requestId).state, "START_UNKNOWN");
  } finally { store.close(); }
});

test("thread mismatch fails closed", () => {
  assert.throws(
    () => summarizeThreadForReconciliation({ thread: { id: "other", turns: [] } }, "expected"),
    { code: "THREAD_ID_MISMATCH" }
  );
});
