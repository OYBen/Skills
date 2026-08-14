import path from "node:path";
import { mkdir } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { prepareGeneratedText } from "./watermark.js";
import { hashIdentifier, sha256, writeFileAtomic } from "./util.js";
import { ControllerError } from "./errors.js";

export async function prepareTextDelivery(context) {
  const { config, store, requestId, sourceText, target } = context;
  if (!target?.conversationId || !target?.referenceMessageId || !target?.referenceSenderOpenDingTalkId) {
    throw new ControllerError("DELIVERY_TARGET_INCOMPLETE", "Delivery target is incomplete");
  }
  context.assertLease?.();
  const prepared = await prepareGeneratedText(sourceText, context.watermarkOptions);
  context.assertLease?.();
  if (!prepared.metrics.withinLimit) {
    throw new ControllerError("DELIVERY_LONG_MESSAGE_UNIMPLEMENTED", "Long-message attachment preparation is not implemented yet");
  }
  await mkdir(config.paths.payloads, { recursive: true });
  context.assertLease?.();
  const deliveryId = randomUUID();
  const payloadPath = path.join(config.paths.payloads, `${deliveryId}.txt`);
  await writeFileAtomic(payloadPath, prepared.text);
  context.assertLease?.();
  const approvalState = new Set(["trusted-service-account", "trusted-self"]).has(config.delivery.mode)
    ? "TRUSTED_IDENTITY_RECHECK_REQUIRED"
    : "AWAITING_SEND_APPROVAL";
  const create = () => store.createDelivery({
    deliveryId,
    requestId,
    kind: context.kind ?? "quoted-text",
    targetConversationId: target.conversationId,
    referenceMessageId: target.referenceMessageId,
    referenceSenderId: target.referenceSenderOpenDingTalkId,
    payloadPath,
    payloadSha256: sha256(prepared.text),
    payloadCodepoints: prepared.metrics.characterCount,
    state: approvalState
  });
  const created = context.leaseTransaction ? context.leaseTransaction(create) : create();
  return { ...created, kind: context.kind ?? "quoted-text", state: approvalState, payloadPath, metrics: prepared.metrics };
}

export function assertDeliveryNotAutomaticallySendable(delivery) {
  if (!delivery || !new Set(["AWAITING_SEND_APPROVAL", "TRUSTED_IDENTITY_RECHECK_REQUIRED"]).has(delivery.state)) {
    throw new ControllerError("DELIVERY_STATE", "Delivery is not in a prepared authorization state");
  }
  return true;
}

export function resolveEnrolledDeliveryTarget(delivery, job, config) {
  if (!delivery || !job || delivery.request_id !== job.request_id) {
    throw new ControllerError("DELIVERY_RECOVERY_MISMATCH", "Delivery and job do not match");
  }
  const target = {
    conversationId: config.channel.conversationId,
    referenceMessageId: job.message_id,
    referenceSenderOpenDingTalkId: config.channel.peerOpenDingTalkId
  };
  if (hashIdentifier(target.conversationId) !== delivery.target_conversation_hash ||
      hashIdentifier(target.referenceMessageId) !== delivery.reference_message_hash ||
      hashIdentifier(target.referenceSenderOpenDingTalkId) !== delivery.reference_sender_hash) {
    throw new ControllerError("DELIVERY_RECOVERY_MISMATCH", "Enrolled delivery target no longer matches immutable hashes");
  }
  return target;
}
