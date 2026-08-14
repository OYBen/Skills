import test from "node:test";
import assert from "node:assert/strict";
import {
  authorizeMessage, enrichEnrolledSelfChatMessage, normalizeDingTalkMessage
} from "../src/normalizer.js";

const config = {
  channel: {
    kind: "direct",
    conversationId: "conv-1",
    peerUserId: "peer-user",
    peerOpenDingTalkId: "peer-open",
    selfUserId: "self-user",
    selfOpenDingTalkId: "self-open"
  }
};

function raw(overrides = {}) {
  return {
    openMessageId: "msg-1",
    createTime: "2026-08-13T04:00:00.000Z",
    openConversationId: "conv-1",
    senderUserId: "peer-user",
    senderOpenDingTalkId: "peer-open",
    msgType: "text",
    text: { content: "/codex help" },
    ...overrides
  };
}

test("normalizes required message fields", () => {
  assert.equal(normalizeDingTalkMessage(raw()).text, "/codex help");
});

test("requires conversation and dual sender identity", () => {
  const message = normalizeDingTalkMessage(raw());
  assert.deepEqual(authorizeMessage(message, config), { authorized: true, disposition: "AUTHORIZED" });
  assert.equal(authorizeMessage({ ...message, senderOpenDingTalkId: "wrong" }, config).disposition, "REJECTED_IDENTITY");
  assert.equal(authorizeMessage({ ...message, senderUserId: "wrong" }, config).disposition, "REJECTED_IDENTITY");
  assert.equal(authorizeMessage({ ...message, conversationId: "wrong" }, config).disposition, "REJECTED_CONVERSATION");
});

test("ignores self messages before command parsing", () => {
  const message = normalizeDingTalkMessage(raw({ senderUserId: "self-user", senderOpenDingTalkId: "self-open" }));
  assert.equal(authorizeMessage(message, config).disposition, "IGNORED_SELF");
});

test("accepts explicitly enrolled self-chat commands", () => {
  const selfChatConfig = {
    channel: {
      kind: "self-chat",
      conversationId: "conv-1",
      peerUserId: "self-user",
      peerOpenDingTalkId: "self-open",
      selfUserId: "self-user",
      selfOpenDingTalkId: "self-open"
    }
  };
  const message = normalizeDingTalkMessage(raw({ senderUserId: "self-user", senderOpenDingTalkId: "self-open" }));
  assert.deepEqual(authorizeMessage(message, selfChatConfig), { authorized: true, disposition: "AUTHORIZED" });
  assert.equal(authorizeMessage({ ...message, conversationId: "other" }, selfChatConfig).disposition, "REJECTED_CONVERSATION");
  assert.equal(authorizeMessage({ ...message, senderOpenDingTalkId: "other" }, selfChatConfig).disposition, "REJECTED_IDENTITY");
});

test("fails closed on incomplete message identity", () => {
  const value = raw();
  delete value.senderOpenDingTalkId;
  assert.throws(() => normalizeDingTalkMessage(value), { code: "MESSAGE_FIELD_MISSING" });
});

test("fills only enrolled self-chat fields omitted by the real DWS shape", () => {
  const selfChatConfig = {
    channel: {
      kind: "self-chat",
      conversationId: "conv-1",
      peerUserId: "self-user",
      peerOpenDingTalkId: "self-open",
      selfUserId: "self-user",
      selfOpenDingTalkId: "self-open"
    }
  };
  const realShape = {
    openMessageId: "message",
    createTime: "2026-08-13 16:58:50",
    openConversationId: "conv-1",
    senderOpenDingTalkId: "self-open",
    content: "/codex help"
  };
  const message = normalizeDingTalkMessage(enrichEnrolledSelfChatMessage(realShape, selfChatConfig));
  assert.equal(message.senderUserId, "self-user");
  assert.equal(message.messageType, "text");
  assert.deepEqual(authorizeMessage(message, selfChatConfig), { authorized: true, disposition: "AUTHORIZED" });

  const wrongSender = { ...realShape, senderOpenDingTalkId: "other" };
  assert.throws(
    () => normalizeDingTalkMessage(enrichEnrolledSelfChatMessage(wrongSender, selfChatConfig)),
    { code: "MESSAGE_FIELD_MISSING" }
  );
});
