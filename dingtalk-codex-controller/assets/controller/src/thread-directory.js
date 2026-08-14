import { createReadStream, existsSync, openSync, closeSync, readSync, statSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import readline from "node:readline";
import path from "node:path";
import { ControllerError } from "./errors.js";
import { codePointLength } from "./util.js";

export const DEFAULT_CODEX_STATE_DATABASE = path.join(
  process.env.CODEX_HOME ?? path.join(process.env.USERPROFILE ?? "", ".codex"),
  "state_5.sqlite"
);

function lifecycleTurnId(record) {
  return record?.payload?.turn_id
    ?? record?.payload?.internal_chat_message_metadata_passthrough?.turn_id
    ?? null;
}

function classifyFailureSignal(record) {
  const payload = record?.payload ?? {};
  const type = String(payload.type ?? "").toLowerCase();
  const status = String(payload.status ?? payload.turn?.status ?? "").toLowerCase();
  if (type.includes("interrupt") || type.includes("abort") || type.includes("cancel") || status === "interrupted") {
    return "TURN_INTERRUPTED";
  }
  if (type.includes("fail") || type === "error" || status === "failed") return "TURN_FAILED";
  return null;
}

export async function inspectRolloutTurn(rolloutPath, turnId) {
  if (typeof rolloutPath !== "string" || !rolloutPath || !existsSync(rolloutPath)) {
    return { status: "MISSING", errorCode: "ROLLOUT_UNAVAILABLE" };
  }
  let started = false;
  let superseded = false;
  let failureCode = null;
  let lastAgentMessage = null;
  const input = createReadStream(rolloutPath, { encoding: "utf8" });
  const lines = readline.createInterface({ input, crlfDelay: Infinity });
  try {
    for await (const line of lines) {
      if (!started && !line.includes(turnId)) continue;
      let record;
      try { record = JSON.parse(line); } catch { continue; }
      const recordTurnId = lifecycleTurnId(record);
      if (record.type === "event_msg" && record.payload?.type === "task_started" && recordTurnId === turnId) {
        started = true;
        continue;
      }
      if (started && record.type === "event_msg" && record.payload?.type === "task_started" &&
          recordTurnId && recordTurnId !== turnId) {
        superseded = true;
        continue;
      }
      if (record.type === "event_msg" && record.payload?.type === "task_complete" && recordTurnId === turnId) {
        const text = typeof record.payload.last_agent_message === "string"
          ? record.payload.last_agent_message.trim()
          : "";
        return text
          ? { status: "COMPLETED", resultText: text, completedAt: record.timestamp ?? null }
          : { status: "FAILED", errorCode: "TURN_RESULT_MISSING", completedAt: record.timestamp ?? null };
      }
      if (recordTurnId !== turnId) continue;
      failureCode = classifyFailureSignal(record) ?? failureCode;
      if (record.type === "response_item" && record.payload?.type === "message" &&
          record.payload?.phase === "final_answer") {
        const text = record.payload.content?.find?.((item) => item?.type === "output_text")?.text;
        if (typeof text === "string" && text.trim()) lastAgentMessage = text.trim();
      }
    }
  } finally {
    lines.close();
    input.destroy();
  }
  if (superseded) return { status: "FAILED", errorCode: "TURN_INTERRUPTED" };
  if (failureCode) return { status: "FAILED", errorCode: failureCode };
  if (started) return { status: "RUNNING", lastAgentMessage };
  return { status: "MISSING", errorCode: "TURN_NOT_PERSISTED_YET" };
}

function readFileTail(rolloutPath, maxBytes = 256 * 1024) {
  const size = statSync(rolloutPath).size;
  const start = Math.max(0, size - maxBytes);
  const length = size - start;
  const buffer = Buffer.alloc(length);
  const descriptor = openSync(rolloutPath, "r");
  try {
    readSync(descriptor, buffer, 0, length, start);
  } finally {
    closeSync(descriptor);
  }
  let text = buffer.toString("utf8");
  if (start > 0) text = text.slice(text.indexOf("\n") + 1);
  return text;
}

function inferLatestStatus(rolloutPath, archived) {
  if (archived) return "archived";
  if (typeof rolloutPath !== "string" || !rolloutPath || !existsSync(rolloutPath)) return "unknown";
  let latestLifecycle = null;
  try {
    for (const line of readFileTail(rolloutPath).split(/\r?\n/gu)) {
      if (!line.includes("task_started") && !line.includes("task_complete")) continue;
      let record;
      try { record = JSON.parse(line); } catch { continue; }
      if (record.type !== "event_msg") continue;
      const turnId = lifecycleTurnId(record);
      if (!turnId) continue;
      if (record.payload?.type === "task_started") {
        latestLifecycle = { type: "started", timestamp: record.timestamp ?? null };
      } else if (record.payload?.type === "task_complete") {
        latestLifecycle = { type: "completed", timestamp: record.timestamp ?? null };
      }
    }
  } catch {
    return "unknown";
  }
  if (!latestLifecycle) return "unknown";
  if (latestLifecycle.type === "completed") return "idle";
  const ageMs = latestLifecycle.timestamp
    ? Date.now() - new Date(latestLifecycle.timestamp).getTime()
    : Number.POSITIVE_INFINITY;
  return Number.isFinite(ageMs) && ageMs < 24 * 60 * 60 * 1000 ? "active" : "unknown";
}

export async function listAllThreads(source = null, options = {}) {
  if (source && typeof source.listThreads === "function") {
    return listLegacyThreads(source, options);
  }
  const databasePath = typeof source === "string"
    ? source
    : source?.stateDatabasePath ?? options.stateDatabasePath ?? DEFAULT_CODEX_STATE_DATABASE;
  let database;
  try {
    database = new DatabaseSync(databasePath, { readOnly: true });
    const rows = database.prepare(`
      SELECT id, rollout_path, cwd, title, name, archived,
             COALESCE(updated_at_ms, updated_at * 1000) AS updated_at_ms
      FROM threads
      ORDER BY COALESCE(updated_at_ms, updated_at * 1000) DESC, id ASC
    `).all();
    const threads = [];
    for (const row of rows) {
      const archived = Boolean(row.archived);
      threads.push({
        id: row.id,
        name: row.name || row.title || null,
        title: row.title || null,
        cwd: row.cwd,
        rolloutPath: row.rollout_path,
        archived,
        updatedAt: Number(row.updated_at_ms ?? 0),
        status: { type: inferLatestStatus(row.rollout_path, archived) }
      });
    }
    return threads;
  } catch (error) {
    throw new ControllerError("THREAD_DIRECTORY_UNAVAILABLE", "Codex Desktop task directory is unavailable", {
      cause: error.code ?? error.message
    });
  } finally {
    database?.close();
  }
}

async function drainLegacyThreads(codexClient, archived, options = {}) {
  const maxPages = options.maxPages ?? 200;
  const seenCursors = new Set();
  const items = [];
  let cursor = null;
  for (let page = 0; page < maxPages; page += 1) {
    const response = await codexClient.listThreads({ archived, cursor, limit: options.limit ?? 100 });
    if (!Array.isArray(response?.data)) {
      throw new ControllerError("THREAD_LIST_INVALID", "Codex returned an invalid task list");
    }
    items.push(...response.data.map((thread) => ({ ...thread, archived })));
    if (!response.nextCursor) return items;
    if (seenCursors.has(response.nextCursor)) {
      throw new ControllerError("THREAD_LIST_CURSOR_LOOP", "Codex task pagination repeated a cursor");
    }
    seenCursors.add(response.nextCursor);
    cursor = response.nextCursor;
  }
  throw new ControllerError("THREAD_LIST_PAGE_LIMIT", "Codex task pagination exceeded the safety limit");
}

async function listLegacyThreads(codexClient, options) {
  const active = await drainLegacyThreads(codexClient, false, options);
  const archived = await drainLegacyThreads(codexClient, true, options);
  const byId = new Map();
  for (const thread of [...active, ...archived]) {
    if (typeof thread.id === "string" && !byId.has(thread.id)) byId.set(thread.id, thread);
  }
  return [...byId.values()].sort((left, right) =>
    Number(right.updatedAt ?? 0) - Number(left.updatedAt ?? 0) || left.id.localeCompare(right.id));
}

function truncateName(value, limit = 42) {
  const text = String(value || "未命名任务")
    .replace(/[\u0000-\u001F\u007F]/gu, " ")
    .replace(/\s+/gu, " ")
    .trim() || "未命名任务";
  if (codePointLength(text) <= limit) return text;
  return `${Array.from(text).slice(0, limit - 1).join("")}…`;
}

export function formatThreadPage(threads, requestedPage, options = {}) {
  const pageSize = options.pageSize ?? 3;
  const pageCount = Math.max(1, Math.ceil(threads.length / pageSize));
  if (requestedPage > pageCount) {
    return `页码超出范围。当前共 ${threads.length} 个 Codex 任务，${pageCount} 页；请使用 /codex threads <1-${pageCount}>。`;
  }
  const start = (requestedPage - 1) * pageSize;
  const rows = threads.slice(start, start + pageSize).map((thread, index) => {
    const fallback = `${threadStatusType(thread)}，${thread.archived ? "已归档" : "未归档"}`;
    const state = options.statusLabels?.get(thread.id) ?? fallback;
    return `${start + index + 1}. ${truncateName(thread.name)}\nID: ${thread.id}\n状态: ${state}`;
  });
  if (rows.length === 0) rows.push("未找到 Codex 任务。");
  return `Codex 任务 ${requestedPage}/${pageCount} 页，共 ${threads.length} 个：\n${rows.join("\n")}`;
}

export function threadStatusType(thread) {
  return typeof thread?.status === "string" ? thread.status : thread?.status?.type ?? "unknown";
}
