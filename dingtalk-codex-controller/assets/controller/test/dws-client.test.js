import test from "node:test";
import assert from "node:assert/strict";
import {
  DwsClient, drainCommandPages, extractPage, resolveCurrentDwsIdentity, verifyCurrentDwsIdentity
} from "../src/dws-client.js";

test("always appends JSON format to dws calls", async () => {
  let captured;
  const client = new DwsClient({ execute: async (file, args) => {
    captured = { file, args };
    return { code: 0, stdout: "{\"success\":true}", stderr: "" };
  }});
  await client.getSelf();
  assert.equal(captured.file, "dws");
  assert.deepEqual(captured.args.slice(-2), ["--format", "json"]);
});

test("rejects explicit DWS failures even when the process exits successfully", async () => {
  const client = new DwsClient({ execute: async () => ({
    code: 0,
    stdout: JSON.stringify({ success: false, error: { message: "denied" } }),
    stderr: ""
  }) });
  await assert.rejects(client.getSelf(), { code: "DWS_REMOTE_FAILED" });
});

test("fails closed on malformed page shapes", () => {
  assert.deepEqual(extractPage({ success: true, result: { hasMore: false, nextCursor: "" } }), {
    items: [], nextCursor: null, hasMore: false
  });
  assert.throws(() => extractPage({ success: true, result: {} }), { code: "DWS_PAGE_SHAPE" });
  assert.throws(() => extractPage({ success: true, result: { items: [], hasMore: "false" } }), { code: "DWS_PAGE_SHAPE" });
});

test("flattens the real nested conversation message shape", () => {
  assert.deepEqual(extractPage({
    success: true,
    result: {
      conversationMessagesList: [{
        openConversationId: "conv",
        messages: [{ openMessageId: "message", content: "/codex help" }]
      }],
      hasMore: false,
      nextCursor: "unused-when-complete"
    }
  }), {
    items: [{ openMessageId: "message", content: "/codex help", openConversationId: "conv" }],
    nextCursor: "unused-when-complete",
    hasMore: false
  });
  assert.throws(() => extractPage({
    success: true,
    result: { conversationMessagesList: [{ openConversationId: "conv" }], hasMore: false }
  }), { code: "DWS_PAGE_SHAPE" });
});

test("resolves and verifies the current DWS dual identity", async () => {
  const client = {
    getSelf: async () => ({ result: [{ orgEmployeeModel: { orgUserName: "Fixture User", userId: "self-user" } }] }),
    searchPersonByName: async () => ({ result: [{ meta: { name: "Fixture User" }, userId: "self-user", openDingTalkId: "self-open" }] })
  };
  assert.deepEqual(await resolveCurrentDwsIdentity(client), { userId: "self-user", openDingTalkId: "self-open" });
  assert.deepEqual(await verifyCurrentDwsIdentity(client, {
    selfUserId: "self-user", selfOpenDingTalkId: "self-open"
  }), { verified: true });
  await assert.rejects(verifyCurrentDwsIdentity(client, {
    selfUserId: "other", selfOpenDingTalkId: "self-open"
  }), { code: "DWS_SESSION_IDENTITY_MISMATCH" });
});

test("drains returned cursors only", async () => {
  const cursors = [];
  const client = {
    async searchCommands({ cursor }) {
      cursors.push(cursor);
      if (cursor === "0") return { result: { items: [{ openMessageId: "1" }], hasMore: true, nextCursor: "opaque" } };
      return { result: { items: [{ openMessageId: "2" }], hasMore: false } };
    }
  };
  const result = await drainCommandPages(client, {}, { maxPages: 3 });
  assert.deepEqual(cursors, ["0", "opaque"]);
  assert.equal(result.items.length, 2);
});

test("fails closed on cursor loop or missing continuation", async () => {
  await assert.rejects(
    drainCommandPages({ searchCommands: async () => ({ result: { items: [], hasMore: true, nextCursor: "0" } }) }, {}, { maxPages: 3 }),
    { code: "POLL_CURSOR_LOOP" }
  );
  await assert.rejects(
    drainCommandPages({ searchCommands: async () => ({ result: { items: [], hasMore: true } }) }, {}, { maxPages: 3 }),
    { code: "POLL_CURSOR_MISSING" }
  );
});
