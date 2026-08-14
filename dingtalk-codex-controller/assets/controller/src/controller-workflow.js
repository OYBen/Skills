import path from "node:path";
import { mkdir } from "node:fs/promises";
import { commandHelp } from "./command-parser.js";
import { startFixedAction, startTargetInstruction, completeLocalJob, preflightTargetInstruction, reconcileRunningJob } from "./job-runner.js";
import { formatThreadPage, listAllThreads } from "./thread-directory.js";
import { availabilityLabel, resolveThreadSelector, threadLabel } from "./thread-routing.js";
import { prepareTextDelivery } from "./outbox.js";
import { sendTrustedDelivery } from "./delivery-worker.js";
import { isoNow, readUtf8, sha256 } from "./util.js";
import { ControllerError, publicError } from "./errors.js";

function fenced(context, callback) {
  return context.leaseTransaction ? context.leaseTransaction(callback) : callback();
}

function rethrowLeaseLoss(error) {
  if (error?.code === "CONTROLLER_LEASE_LOST") throw error;
}

function resultPath(config, requestId) {
  return path.join(config.paths.payloads, `${requestId}.result.txt`);
}

function summarizeJob(job) {
  if (!job) return "尚无已登记指令。";
  const action = job.action_alias ? `，动作 ${job.action_alias}` : "";
  return `请求 ${job.request_id}：${job.command}${action}，状态 ${job.state}。`;
}

function bindingText(binding, threads) {
  const describe = (threadId) => {
    if (!threadId) return "未设置";
    const thread = threads.find((item) => item.id === threadId);
    return thread ? `${threadLabel(thread)}（${threadId}）` : `${threadId}（当前目录未找到）`;
  };
  return `指令目标：${describe(binding?.target_thread_id)}\n监控对象：${describe(binding?.watch_thread_id)}`;
}

async function threadListText(job, context) {
  const threads = await listAllThreads(context.threadDirectory);
  const page = Number(job.thread_page ?? 1);
  const pageSize = 3;
  const start = (page - 1) * pageSize;
  const visible = threads.slice(start, start + pageSize);
  const statusLabels = new Map();
  for (const thread of visible) {
    let ownerAvailable = null;
    if (!thread.archived && (typeof thread.status === "string" ? thread.status : thread.status?.type) === "idle") {
      ownerAvailable = context.desktopClient ? Boolean(await context.desktopClient.findThreadOwner(thread.id)) : false;
      context.assertLease?.();
    }
    statusLabels.set(thread.id, availabilityLabel(thread, ownerAvailable));
  }
  fenced(context, () => context.store.saveThreadSelections(
    context.config.channel.conversationId,
    visible.map((thread, index) => ({ number: start + index + 1, threadId: thread.id })),
    context.config.limits?.threadSelectionTtlSeconds ?? 3600
  ));
  return formatThreadPage(threads, page, { pageSize, statusLabels });
}

async function bindingCommandText(job, context) {
  const { config, store } = context;
  const threads = await listAllThreads(context.threadDirectory);
  const current = store.getBinding(config.channel.conversationId);
  if (!job.target_selector) return bindingText(current, threads);
  if (job.target_selector.toLocaleLowerCase("zh-CN") === "clear") {
    const values = job.command === "target" ? { targetThreadId: null } : { watchThreadId: null };
    const updated = fenced(context, () => store.setBinding(config.channel.conversationId, values));
    return `${job.command === "target" ? "指令目标" : "监控对象"}已清除。\n${bindingText(updated, threads)}`;
  }
  const target = resolveThreadSelector(job.target_selector, threads, {
    store,
    conversationId: config.channel.conversationId
  });
  if (target.archived) throw new ControllerError("THREAD_ARCHIVED", "不能绑定已归档的 Codex 任务");
  const values = job.command === "target"
    ? { targetThreadId: target.id }
    : { watchThreadId: target.id };
  const updated = fenced(context, () => store.setBinding(config.channel.conversationId, values));
  return `${job.command === "target" ? "指令目标" : "监控对象"}已绑定到 ${threadLabel(target)}。\n${bindingText(updated, threads)}`;
}

function queueText(context) {
  const queued = context.store.queuedJobs(5);
  if (queued.length === 0) return "当前没有排队请求。";
  const reasonText = (reason) => reason === "THREAD_ACTIVE"
    ? "目标执行中"
    : reason === "DESKTOP_THREAD_OWNER_UNAVAILABLE"
      ? "等待 Desktop 打开"
      : "等待预检";
  return `当前排队请求：\n${queued.map((job, index) =>
    `${index + 1}. ${job.request_id}，目标 ${job.target_thread_id ?? job.target_selector ?? "未解析"}，${reasonText(job.queue_reason)}`
  ).join("\n")}`;
}

function cancelText(job, context) {
  const canceled = fenced(context, () => context.store.cancelQueuedJob(job.requested_request_id));
  return canceled
    ? `已取消排队请求 ${canceled.request_id}。`
    : "未找到可取消的排队请求。";
}

async function localResultText(job, context) {
  const { store } = context;
  if (job.command === "help") return `可用指令：\n${commandHelp}`;
  if (job.command === "status") {
    const threads = await listAllThreads(context.threadDirectory);
    return `${bindingText(store.getBinding(context.config.channel.conversationId), threads)}\n${summarizeJob(store.latestJob({ excludeRequestId: job.request_id }))}`;
  }
  if (job.command === "threads") return threadListText(job, context);
  if (job.command === "target" || job.command === "watch") return bindingCommandText(job, context);
  if (job.command === "queue") return queueText(context);
  if (job.command === "cancel") return cancelText(job, context);
  if (job.command === "result") {
    const target = job.requested_request_id
      ? store.getJob(job.requested_request_id)
      : store.latestJob({ excludeRequestId: job.request_id });
    if (!target) return "没有可返回的请求结果。";
    if (target.state === "COMPLETED" || target.state === "DELIVERED") {
      if (!target.result_path) return `${summarizeJob(target)} 结果文件缺失。`;
      const text = await readUtf8(target.result_path);
      if (sha256(text) !== target.result_sha256) throw new ControllerError("RESULT_HASH_MISMATCH", "Stored result failed integrity verification");
      return `请求 ${target.request_id} 的结果：\n${text}`;
    }
    return summarizeJob(target);
  }
  throw new ControllerError("LOCAL_COMMAND_UNSUPPORTED", "Command requires Codex execution");
}

async function prepareReply(context, job, sourceText, kind) {
  const { config, store } = context;
  const existing = store.getDeliveryForRequest(job.request_id, kind);
  if (existing) return existing;
  const target = {
    conversationId: config.channel.conversationId,
    referenceMessageId: job.message_id,
    referenceSenderOpenDingTalkId: config.channel.peerOpenDingTalkId
  };
  try {
    return await prepareTextDelivery({
      ...context, config, store, requestId: job.request_id, sourceText, kind, target
    });
  } catch (error) {
    if (kind !== "result" || error?.code !== "DELIVERY_LONG_MESSAGE_UNIMPLEMENTED") throw error;
    fenced(context, () => store.audit("DELIVERY_RESULT_OVER_LIMIT", { limit: 500 }, job.request_id));
    return prepareTextDelivery({
      config,
      store,
      assertLease: context.assertLease,
      leaseTransaction: context.leaseTransaction,
      requestId: job.request_id,
      sourceText: `请求 ${job.request_id} 已处理，但结果超过 500 字符，未通过钉钉发送完整内容；请在本机核查。`,
      kind,
      target
    });
  }
}

const NOTIFIED_STATE = new Map([
  ["COMPLETED", "DELIVERED"],
  ["FAILED", "FAILED_NOTIFIED"],
  ["START_UNKNOWN", "START_UNKNOWN_NOTIFIED"]
]);

function persistDeliveryOutcome(context, job, deliveryKind) {
  const { store } = context;
  if (deliveryKind === "ack") {
    if (!new Set(["PENDING", "QUEUED"]).has(job.state) ||
        !fenced(context, () => store.transitionJob(job.request_id, job.state, "ACK_SENT"))) {
      throw new ControllerError("JOB_RACE", "Job state changed after acknowledgement delivery");
    }
    return;
  }
  const nextState = NOTIFIED_STATE.get(job.state);
  if (nextState && !fenced(context, () => store.transitionJob(job.request_id, job.state, nextState))) {
    throw new ControllerError("JOB_RACE", "Job state changed after result delivery");
  }
}

function queuedDescription(job, preflight, position) {
  const name = threadLabel(preflight.target);
  if (preflight.reason === "THREAD_ACTIVE") {
    return `请求 ${job.request_id} 已排队（位置 ${position}）：目标任务 ${name} 正在执行；当前轮次结束后自动发送。`;
  }
  return `请求 ${job.request_id} 已排队（位置 ${position}）：目标任务 ${name} 未由 Codex Desktop 窗口加载；打开后自动发送。`;
}

async function preflightAndNotify(context, job, events) {
  try {
    const preflight = await preflightTargetInstruction({ ...context, requestId: job.request_id });
    if (preflight.status === "QUEUED") {
      if (!fenced(context, () => context.store.transitionJob(job.request_id, job.state, "QUEUED", {
        target_thread_id: preflight.target.id,
        queue_reason: preflight.reason
      }))) throw new ControllerError("JOB_RACE", "Job state changed during queue preflight");
      const queuedJob = context.store.getJob(job.request_id);
      const delivery = await prepareReply(
        context,
        queuedJob,
        queuedDescription(queuedJob, preflight, context.store.queuePosition(job.request_id)),
        "queued"
      );
      events.push({ requestId: job.request_id, phase: "queued", ...(await deliverPrepared(context, queuedJob, delivery)) });
      return;
    }
    if (!fenced(context, () => context.store.transitionJob(job.request_id, job.state, job.state, {
      target_thread_id: preflight.target.id,
      queue_reason: null
    }))) throw new ControllerError("JOB_RACE", "Job state changed during ready preflight");
    const readyJob = context.store.getJob(job.request_id);
    const description = `请求 ${job.request_id} 预检通过：目标任务 ${threadLabel(preflight.target)} 已空闲并加载，开始执行。`;
    const ack = await prepareReply(context, readyJob, description, "ack");
    events.push({ requestId: job.request_id, phase: "ack", ...(await deliverPrepared(context, readyJob, ack)) });
  } catch (error) {
    rethrowLeaseLoss(error);
    const failed = fenced(context, () => context.store.transitionJob(job.request_id, job.state, "FAILED", {
      completed_at: isoNow(context.clock),
      error_code: error.code ?? "PREFLIGHT_FAILED"
    }));
    if (!failed) throw new ControllerError("JOB_RACE", "Job state changed during failed preflight");
    fenced(context, () => context.store.audit("WORKFLOW_ERROR", publicError(error), job.request_id));
    events.push({ requestId: job.request_id, phase: "preflight", status: "ERROR", error: publicError(error) });
  }
}

const FAILURE_TEXT = new Map([
  ["TARGET_NOT_BOUND", "尚未设置指令目标，请先使用 /codex target <名称|编号|ID>。"],
  ["THREAD_SELECTION_EXPIRED", "任务短编号不存在或已过期，请重新执行 /codex threads。"],
  ["THREAD_SELECTOR_AMBIGUOUS", "任务名称不唯一，请使用 /codex threads 返回的短编号或完整 ID。"],
  ["THREAD_NOT_FOUND", "未找到目标 Codex 任务，请重新执行 /codex threads。"],
  ["THREAD_ARCHIVED", "目标 Codex 任务已归档，不能接收指令。"],
  ["THREAD_STATUS_UNKNOWN", "无法确认目标任务为空闲状态，本次未发送。"],
  ["DESKTOP_IPC_UNAVAILABLE", "Codex Desktop IPC 当前不可用，本次未发送。"]
]);

function failureText(job) {
  const detail = FAILURE_TEXT.get(job.error_code);
  return detail
    ? `请求 ${job.request_id} 未执行：${detail}`
    : `请求 ${job.request_id} 执行失败，错误码 ${job.error_code ?? "UNKNOWN"}。`;
}

async function deliverPrepared(context, job, delivery) {
  if (delivery.state === "SENT") {
    if (delivery.kind === "ack" && job.state === "PENDING") persistDeliveryOutcome(context, job, "ack");
    else if (NOTIFIED_STATE.has(job.state)) persistDeliveryOutcome(context, job, delivery.kind);
    return { status: "SENT", alreadySent: true };
  }
  if (delivery.state !== "TRUSTED_IDENTITY_RECHECK_REQUIRED") return { status: delivery.state };
  const sent = await sendTrustedDelivery({ ...context, deliveryId: delivery.delivery_id ?? delivery.deliveryId });
  if (sent.status !== "SENT") return sent;
  persistDeliveryOutcome(context, job, delivery.kind ?? "");
  return sent;
}

export async function advanceController(context) {
  const { config, store } = context;
  await mkdir(config.paths.payloads, { recursive: true });
  const events = [];

  for (const job of store.listJobsByStates(["PENDING"], 20)) {
    try {
      if (job.command === "send") {
        await preflightAndNotify(context, job, events);
      } else if (job.command === "run") {
        const description = `已接受请求 ${job.request_id}，准备启动只读 Codex 动作 ${job.action_alias}。`;
        const ack = await prepareReply(context, job, description, "ack");
        events.push({ requestId: job.request_id, phase: "ack", ...(await deliverPrepared(context, job, ack)) });
      } else {
        const text = await localResultText(job, context);
        events.push({ requestId: job.request_id, phase: "local", ...(await completeLocalJob({
          ...context, store, requestId: job.request_id, resultText: text, resultPath: resultPath(config, job.request_id)
        })) });
      }
    } catch (error) {
      rethrowLeaseLoss(error);
      if (!new Set(["run", "send"]).has(job.command)) {
        fenced(context, () => store.transitionJob(job.request_id, "PENDING", "FAILED", {
          completed_at: isoNow(context.clock), error_code: error.code ?? "LOCAL_COMMAND_FAILED"
        }));
      }
      fenced(context, () => store.audit("WORKFLOW_ERROR", publicError(error), job.request_id));
      events.push({ requestId: job.request_id, phase: "pending", status: "ERROR", error: publicError(error) });
    }
  }

  for (const job of store.listJobsByStates(["QUEUED"], 20)) {
    await preflightAndNotify(context, job, events);
  }

  for (const job of store.listJobsByStates(["ACK_SENT"], 10)) {
    try {
      const starter = job.command === "send" ? startTargetInstruction : startFixedAction;
      const codexClient = job.command === "run" && !context.codexClient
        ? await context.getCodexClient?.()
        : context.codexClient;
      events.push({ requestId: job.request_id, phase: "start", ...(await starter({
        ...context, codexClient, requestId: job.request_id, gates: context.gates
      })) });
    } catch (error) {
      rethrowLeaseLoss(error);
      if (job.command === "send" && new Set(["THREAD_ACTIVE", "DESKTOP_THREAD_OWNER_UNAVAILABLE"]).has(error.code)) {
        fenced(context, () => store.transitionJob(job.request_id, "ACK_SENT", "QUEUED", { queue_reason: error.code }));
        events.push({ requestId: job.request_id, phase: "start", status: "QUEUED", reason: error.code });
        continue;
      }
      fenced(context, () => store.transitionJob(job.request_id, "ACK_SENT", "FAILED", {
        completed_at: isoNow(context.clock), error_code: error.code ?? "START_FAILED"
      }));
      fenced(context, () => store.audit("WORKFLOW_ERROR", publicError(error), job.request_id));
      events.push({ requestId: job.request_id, phase: "start", status: "ERROR", error: publicError(error) });
    }
  }

  for (const job of store.listJobsByStates(["RUNNING"], 10)) {
    try {
      events.push({ requestId: job.request_id, phase: "reconcile", ...(await reconcileRunningJob({
        ...context, requestId: job.request_id, resultPath: resultPath(config, job.request_id)
      })) });
    } catch (error) {
      rethrowLeaseLoss(error);
      fenced(context, () => store.audit("WORKFLOW_ERROR", publicError(error), job.request_id));
      events.push({ requestId: job.request_id, phase: "reconcile", status: "ERROR", error: publicError(error) });
    }
  }

  for (const job of store.listJobsByStates(["COMPLETED", "FAILED", "START_UNKNOWN"], 20)) {
    try {
      let text;
      if (job.state === "COMPLETED") text = await readUtf8(job.result_path);
      else if (job.state === "START_UNKNOWN") text = `请求 ${job.request_id} 的 Codex 启动结果不确定，已停止自动重试，需要本地核查。`;
      else text = failureText(job);
      const delivery = await prepareReply(context, job, text, "result");
      events.push({ requestId: job.request_id, phase: "delivery", ...(await deliverPrepared(context, job, delivery)) });
    } catch (error) {
      rethrowLeaseLoss(error);
      fenced(context, () => store.audit("WORKFLOW_ERROR", publicError(error), job.request_id));
      events.push({ requestId: job.request_id, phase: "delivery", status: "ERROR", error: publicError(error) });
    }
  }
  return events;
}
