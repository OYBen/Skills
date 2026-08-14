import { readUtf8, sha256, isoNow } from "./util.js";
import { ControllerError } from "./errors.js";
import { resolveEnrolledDeliveryTarget } from "./outbox.js";
import { matchesTrustedRecipient } from "./trusted-policy.js";

function fenced(context, callback) {
  return context.leaseTransaction ? context.leaseTransaction(callback) : callback();
}

function assertLease(context) {
  context.assertLease?.();
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  return value && typeof value === "object" ? [value] : [];
}

function personName(person) {
  return person?.name ?? person?.userName ?? person?.orgUserName
    ?? person?.orgEmployeeModel?.orgUserName ?? person?.meta?.name
    ?? person?.title ?? person?.author ?? null;
}

function responseMessageId(response) {
  const result = response?.result ?? response;
  return result?.openMessageId ?? result?.openMsgId ?? result?.messageId
    ?? result?.msgId ?? result?.message?.openMessageId ?? null;
}

const RETRYABLE_PROCESS_CODES = new Set([
  "PROCESS_TIMEOUT", "EAGAIN", "EBUSY", "EMFILE", "ENFILE", "ENOMEM", "ETIMEDOUT", "ECONNRESET"
]);

function isRetryableProcessFailure(error) {
  return RETRYABLE_PROCESS_CODES.has(error?.code);
}

export async function verifyTrustedSelfRecipient(dwsClient, config) {
  if (config.channel.kind !== "self-chat") {
    throw new ControllerError("TRUSTED_TARGET_MODE", "Automatic trusted delivery is limited to the enrolled self-chat");
  }
  const response = await dwsClient.searchPersonByName(config.delivery.trustedRecipientName);
  const candidates = asArray(response?.result?.items ?? response?.result ?? response?.items);
  const exact = candidates.filter((candidate) => personName(candidate) === config.delivery.trustedRecipientName);
  if (exact.length !== 1) {
    throw new ControllerError("TRUSTED_TARGET_AMBIGUOUS", "Trusted recipient lookup was not unique");
  }
  const candidate = exact[0];
  const userId = String(candidate?.userId ?? candidate?.orgEmployeeModel?.userId ?? "");
  const openDingTalkId = String(candidate?.openDingTalkId ?? candidate?.openDingtalkId
    ?? candidate?.orgEmployeeModel?.openDingTalkId ?? "");
  if (!matchesTrustedRecipient(userId, openDingTalkId) ||
      userId !== config.channel.peerUserId || openDingTalkId !== config.channel.peerOpenDingTalkId ||
      userId !== config.channel.selfUserId || openDingTalkId !== config.channel.selfOpenDingTalkId) {
    throw new ControllerError("TRUSTED_TARGET_IDENTITY_MISMATCH", "Trusted recipient dual identity did not match enrollment");
  }
  return { verified: true };
}

export async function sendTrustedDelivery(context) {
  const { config, store, dwsClient, deliveryId } = context;
  const delivery = store.getDelivery(deliveryId);
  if (!delivery || delivery.state !== "TRUSTED_IDENTITY_RECHECK_REQUIRED") {
    throw new ControllerError("DELIVERY_STATE", "Delivery is not ready for trusted-recipient verification");
  }
  const job = store.getJob(delivery.request_id);
  const target = resolveEnrolledDeliveryTarget(delivery, job, config);
  const text = await readUtf8(delivery.payload_path);
  if (sha256(text) !== delivery.payload_sha256 || Array.from(text).length !== delivery.payload_codepoints) {
    throw new ControllerError("DELIVERY_PAYLOAD_MISMATCH", "Persisted delivery payload failed integrity verification");
  }
  if (!text.startsWith("【AI生成】\n")) {
    throw new ControllerError("DELIVERY_WATERMARK_MISSING", "Delivery payload is missing the generated AI watermark");
  }
  try {
    assertLease(context);
    await verifyTrustedSelfRecipient(dwsClient, config);
    assertLease(context);
  } catch (error) {
    if (error?.code === "CONTROLLER_LEASE_LOST") throw error;
    fenced(context, () => store.transitionDelivery(deliveryId, "TRUSTED_IDENTITY_RECHECK_REQUIRED", "AWAITING_SEND_APPROVAL", {
      last_error_code: error.code ?? "TRUSTED_TARGET_CHECK_FAILED"
    }));
    return { status: "AWAITING_SEND_APPROVAL", errorCode: error.code ?? "TRUSTED_TARGET_CHECK_FAILED" };
  }
  if (!fenced(context, () => store.transitionDelivery(deliveryId, "TRUSTED_IDENTITY_RECHECK_REQUIRED", "SEND_CALL_IN_FLIGHT", {
    attempt_count: delivery.attempt_count + 1
  }))) throw new ControllerError("DELIVERY_RACE", "Delivery state changed before send");

  let response;
  try {
    assertLease(context);
    response = await dwsClient.replyMessage({
      conversationId: target.conversationId,
      referenceMessageId: target.referenceMessageId,
      referenceSenderOpenDingTalkId: target.referenceSenderOpenDingTalkId,
      text,
      uuid: delivery.dws_uuid
    });
    assertLease(context);
  } catch (firstError) {
    if (firstError?.code === "CONTROLLER_LEASE_LOST") throw firstError;
    if (!isRetryableProcessFailure(firstError)) {
      const state = firstError?.code === "DWS_REMOTE_FAILED" ? "SEND_FAILED" : "DELIVERY_UNKNOWN";
      fenced(context, () => store.transitionDelivery(deliveryId, "SEND_CALL_IN_FLIGHT", state, {
        last_error_code: firstError.code ?? "DWS_SEND_FAILED"
      }));
      return { status: state, errorCode: firstError.code ?? "DWS_SEND_FAILED" };
    }
    try {
      assertLease(context);
      response = await dwsClient.replyMessage({
        conversationId: target.conversationId,
        referenceMessageId: target.referenceMessageId,
        referenceSenderOpenDingTalkId: target.referenceSenderOpenDingTalkId,
        text,
        uuid: delivery.dws_uuid
      }, { verbose: true });
      assertLease(context);
    } catch (secondError) {
      if (secondError?.code === "CONTROLLER_LEASE_LOST") throw secondError;
      fenced(context, () => store.transitionDelivery(deliveryId, "SEND_CALL_IN_FLIGHT", "DELIVERY_UNKNOWN", {
        attempt_count: delivery.attempt_count + 2,
        last_error_code: secondError.code ?? firstError.code ?? "DWS_SEND_FAILED"
      }));
      return { status: "DELIVERY_UNKNOWN", errorCode: secondError.code ?? firstError.code ?? "DWS_SEND_FAILED" };
    }
  }
  if (response?.success !== true) {
    fenced(context, () => store.transitionDelivery(deliveryId, "SEND_CALL_IN_FLIGHT", "DELIVERY_UNKNOWN", {
      last_error_code: "DWS_SUCCESS_NOT_EXPLICIT"
    }));
    return { status: "DELIVERY_UNKNOWN", errorCode: "DWS_SUCCESS_NOT_EXPLICIT" };
  }
  const sentAt = isoNow(context.clock);
  const messageId = responseMessageId(response);
  const persisted = fenced(context, () => {
    if (!store.transitionDelivery(deliveryId, "SEND_CALL_IN_FLIGHT", "SENT", { sent_at: sentAt })) return false;
    if (messageId) store.recordOutboundMessage(delivery.dws_uuid, String(messageId));
    return true;
  });
  if (!persisted) {
    throw new ControllerError("DELIVERY_RACE", "Delivery state changed after explicit send success");
  }
  return { status: "SENT", messageIdRecorded: Boolean(messageId) };
}
