import { ControllerError } from "./errors.js";

function first(object, paths) {
  for (const path of paths) {
    let current = object;
    for (const key of path.split(".")) current = current?.[key];
    if (current !== undefined && current !== null && current !== "") return current;
  }
  return undefined;
}

export function enrichEnrolledSelfChatMessage(raw, config) {
  if (!raw || typeof raw !== "object" || config.channel?.kind !== "self-chat") return raw;
  const conversationId = first(raw, ["openConversationId", "conversationId", "conversation.openConversationId"]);
  const senderOpenDingTalkId = first(raw, [
    "senderOpenDingTalkId", "senderOpenDingtalkId", "sender.openDingTalkId"
  ]);
  if (String(conversationId ?? "") !== config.channel.conversationId ||
      String(senderOpenDingTalkId ?? "") !== config.channel.peerOpenDingTalkId ||
      config.channel.peerUserId !== config.channel.selfUserId ||
      config.channel.peerOpenDingTalkId !== config.channel.selfOpenDingTalkId) {
    return raw;
  }

  const enriched = { ...raw };
  if (!first(raw, ["senderUserId", "userId", "sender.userId"])) {
    enriched.senderUserId = config.channel.peerUserId;
  }
  const content = first(raw, ["text.content", "content.text", "content", "text"]);
  const type = first(raw, ["msgType", "messageType", "type"]);
  if (!type && typeof content === "string" && /^\s*\/codex(?:\s|$)/u.test(content)) {
    enriched.msgType = "text";
  }
  return enriched;
}

export function normalizeDingTalkMessage(raw) {
  if (!raw || typeof raw !== "object") {
    throw new ControllerError("MESSAGE_INVALID", "Message is not an object");
  }

  const message = {
    messageId: first(raw, ["openMessageId", "openMsgId", "messageId", "msgId"]),
    createdAt: first(raw, ["createTime", "createdAt", "sendTime", "timestamp"]),
    conversationId: first(raw, ["openConversationId", "conversationId", "conversation.openConversationId"]),
    senderUserId: first(raw, ["senderUserId", "userId", "sender.userId"]),
    senderOpenDingTalkId: first(raw, ["senderOpenDingTalkId", "senderOpenDingtalkId", "sender.openDingTalkId"]),
    messageType: first(raw, ["msgType", "messageType", "type"]),
    text: first(raw, ["text.content", "content.text", "content", "text"])
  };

  for (const [field, value] of Object.entries(message)) {
    if (value === undefined || value === null || value === "") {
      throw new ControllerError("MESSAGE_FIELD_MISSING", `Message is missing ${field}`);
    }
  }

  message.messageId = String(message.messageId);
  message.createdAt = new Date(message.createdAt).toISOString();
  message.conversationId = String(message.conversationId);
  message.senderUserId = String(message.senderUserId);
  message.senderOpenDingTalkId = String(message.senderOpenDingTalkId);
  message.messageType = String(message.messageType).toLowerCase();
  message.text = typeof message.text === "string" ? message.text : String(message.text);
  return message;
}

export function authorizeMessage(message, config) {
  const channel = config.channel;
  if (message.senderUserId === channel.selfUserId &&
      message.senderOpenDingTalkId === channel.selfOpenDingTalkId &&
      channel.kind !== "self-chat") {
    return { authorized: false, disposition: "IGNORED_SELF" };
  }
  if (message.conversationId !== channel.conversationId) {
    return { authorized: false, disposition: "REJECTED_CONVERSATION" };
  }
  if (message.senderUserId !== channel.peerUserId ||
      message.senderOpenDingTalkId !== channel.peerOpenDingTalkId) {
    return { authorized: false, disposition: "REJECTED_IDENTITY" };
  }
  if (!new Set(["text", "txt"]).has(message.messageType)) {
    return { authorized: false, disposition: "IGNORED_NON_TEXT" };
  }
  return { authorized: true, disposition: "AUTHORIZED" };
}
