import { parseCommand } from "./command-parser.js";
import { authorizeMessage, enrichEnrolledSelfChatMessage, normalizeDingTalkMessage } from "./normalizer.js";
import { ControllerError } from "./errors.js";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { rm } from "node:fs/promises";
import { sha256, writeFileAtomic } from "./util.js";

function limitExceeded(config, store, now = new Date()) {
  const fiveMinuteLimit = config.limits?.maxAcceptedPerFiveMinutes ?? 5;
  const hourlyLimit = config.limits?.maxAcceptedPerHour ?? 20;
  const fiveMinutesAgo = new Date(now.getTime() - 5 * 60_000).toISOString();
  const hourAgo = new Date(now.getTime() - 60 * 60_000).toISOString();
  return store.acceptedCountSince(fiveMinutesAgo) >= fiveMinuteLimit ||
    store.acceptedCountSince(hourAgo) >= hourlyLimit;
}

function fenced(context, callback) {
  return context.leaseTransaction ? context.leaseTransaction(callback) : callback();
}

async function persistInstructionCommand(message, parsed, action, initialState, context) {
  const { config, store } = context;
  const binding = store.getBinding(config.channel.conversationId);
  const routed = {
    ...parsed,
    targetThreadId: parsed.useBoundTarget ? binding?.target_thread_id ?? null : parsed.targetThreadId,
    watchThreadId: binding?.watch_thread_id ?? null
  };
  const instructionSha256 = sha256(parsed.instruction);
  const instructionPath = path.join(config.paths.payloads, `instruction-${randomUUID()}.txt`);
  await writeFileAtomic(instructionPath, parsed.instruction);
  let accepted;
  try {
    const persist = () => store.acceptCommand(message, routed, action, initialState, {
      instructionPath, instructionSha256
    });
    accepted = fenced(context, persist);
  } catch (error) {
    await rm(instructionPath, { force: true });
    throw error;
  }
  if (accepted.duplicate) await rm(instructionPath, { force: true });
  return accepted.duplicate
    ? { disposition: "DUPLICATE" }
    : { disposition: "OBSERVED", requestId: accepted.requestId, command: parsed.command };
}

export function processRawMessage(raw, context) {
  const { config, store } = context;
  let message;
  try {
    message = normalizeDingTalkMessage(enrichEnrolledSelfChatMessage(raw, config));
  } catch (error) {
    fenced(context, () => store.audit("MESSAGE_REJECTED_MALFORMED", { code: error.code ?? "MESSAGE_INVALID" }));
    return { disposition: "REJECTED_MALFORMED" };
  }

  if (store.hasMessage(message.messageId)) return { disposition: "DUPLICATE" };
  if (store.hasOutboundMessage(message.messageId)) {
    fenced(context, () => store.recordDisposition(message, "IGNORED_OUTBOUND"));
    return { disposition: "IGNORED_OUTBOUND" };
  }
  const authorization = authorizeMessage(message, config);
  if (!authorization.authorized) {
    fenced(context, () => store.recordDisposition(message, authorization.disposition));
    return { disposition: authorization.disposition };
  }

  let parsed;
  try {
    parsed = parseCommand(message.text);
  } catch (error) {
    const code = error instanceof ControllerError ? error.code : "COMMAND_INVALID";
    fenced(context, () => store.recordDisposition(message, code));
    return { disposition: code };
  }
  if (parsed.kind === "not-command") {
    fenced(context, () => store.recordDisposition(message, "IGNORED_NON_COMMAND"));
    return { disposition: "IGNORED_NON_COMMAND" };
  }

  if (limitExceeded(config, store, context.now ?? new Date())) {
    fenced(context, () => store.recordDisposition(message, "REJECTED_RATE_LIMIT"));
    return { disposition: "REJECTED_RATE_LIMIT" };
  }

  let action = null;
  if (parsed.command === "run") {
    if (config.task?.enrolled === false || !config.task?.threadId) {
      fenced(context, () => store.recordDisposition(message, "REJECTED_TASK_UNENROLLED"));
      return { disposition: "REJECTED_TASK_UNENROLLED" };
    }
    action = config.actions?.[parsed.actionAlias];
    if (!action || action.enabled !== true) {
      fenced(context, () => store.recordDisposition(message, "REJECTED_ACTION_DISABLED"));
      return { disposition: "REJECTED_ACTION_DISABLED" };
    }
  }

  const initialState = config.mode === "active" ? "PENDING" : "OBSERVED";
  if (parsed.command === "send" && initialState === "PENDING") {
    return persistInstructionCommand(message, parsed, action, initialState, context);
  }
  const persist = () => store.acceptCommand(message, parsed, action, initialState);
  const accepted = fenced(context, persist);
  return accepted.duplicate
    ? { disposition: "DUPLICATE" }
    : { disposition: "OBSERVED", requestId: accepted.requestId, command: parsed.command };
}
