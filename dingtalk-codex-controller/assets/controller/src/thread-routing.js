import { ControllerError } from "./errors.js";

const THREAD_ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/iu;
const THREAD_NUMBER = /^[1-9][0-9]{0,2}$/u;

export function threadLabel(thread) {
  return String(thread?.name || thread?.title || "未命名任务").replace(/\s+/gu, " ").trim();
}

function normalizedLabel(value) {
  return String(value ?? "").normalize("NFKC").trim().toLocaleLowerCase("zh-CN");
}

export function resolveThreadSelector(selector, threads, options = {}) {
  const value = String(selector ?? "").trim();
  if (!value) {
    throw new ControllerError("TARGET_NOT_BOUND", "尚未绑定接收指令的 Codex 任务");
  }
  if (THREAD_ID.test(value)) {
    const target = threads.find((thread) => thread.id.toLowerCase() === value.toLowerCase());
    if (!target) throw new ControllerError("THREAD_NOT_FOUND", "Codex 目标任务不存在");
    return target;
  }
  if (THREAD_NUMBER.test(value)) {
    const threadId = options.store?.getThreadSelection(options.conversationId, Number(value));
    if (!threadId) {
      throw new ControllerError("THREAD_SELECTION_EXPIRED", "任务短编号不存在或已过期，请重新执行 /codex threads");
    }
    const target = threads.find((thread) => thread.id === threadId);
    if (!target) throw new ControllerError("THREAD_NOT_FOUND", "短编号对应的 Codex 任务已不存在");
    return target;
  }

  const wanted = normalizedLabel(value);
  const exact = threads.filter((thread) => normalizedLabel(threadLabel(thread)) === wanted);
  if (exact.length === 1) return exact[0];
  if (exact.length > 1) {
    throw new ControllerError("THREAD_SELECTOR_AMBIGUOUS", "任务名称不唯一，请使用 /codex threads 返回的短编号或完整 ID");
  }
  const partial = threads.filter((thread) => normalizedLabel(threadLabel(thread)).includes(wanted));
  if (partial.length === 1) return partial[0];
  if (partial.length > 1) {
    throw new ControllerError("THREAD_SELECTOR_AMBIGUOUS", "任务名称命中多个结果，请使用 /codex threads 返回的短编号或完整 ID");
  }
  throw new ControllerError("THREAD_NOT_FOUND", "未找到与名称匹配的 Codex 任务");
}

export function availabilityLabel(thread, ownerAvailable = null) {
  if (thread.archived) return "已归档，不可发送";
  const status = typeof thread.status === "string" ? thread.status : thread.status?.type;
  if (status === "active") return "执行中，可排队";
  if (status === "idle" && ownerAvailable === true) return "空闲，可立即发送";
  if (status === "idle" && ownerAvailable === false) return "未加载，需在 Codex Desktop 打开";
  return "状态未知，暂不可发送";
}

export function instructionForJob(instruction, watchThreadId) {
  if (!watchThreadId) return instruction;
  return [
    "针对以下监控对象处理用户指令。",
    `监控对象 Codex 任务 ID：${watchThreadId}`,
    `用户指令：${instruction}`
  ].join("\n");
}
