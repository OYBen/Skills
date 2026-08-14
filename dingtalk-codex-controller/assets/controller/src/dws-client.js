import { spawn } from "node:child_process";
import { ControllerError } from "./errors.js";
import { parseJson } from "./util.js";

export function runProcess(file, args, options = {}) {
  const timeoutMs = options.timeoutMs ?? 30_000;
  return new Promise((resolve, reject) => {
    const child = spawn(file, args, {
      cwd: options.cwd,
      windowsHide: true,
      shell: false,
      env: options.env ?? process.env
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (timedOut) {
        reject(new ControllerError("PROCESS_TIMEOUT", `${file} timed out`));
      } else {
        resolve({ code, stdout, stderr });
      }
    });
  });
}

export class DwsClient {
  constructor(options = {}) {
    this.binary = options.binary ?? "dws";
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.execute = options.execute ?? runProcess;
  }

  async invoke(args, options = {}) {
    if (args.includes("--format")) {
      throw new ControllerError("DWS_FORMAT_DUPLICATE", "DWS format is managed by the adapter");
    }
    const finalArgs = [...args];
    if (options.verbose) finalArgs.push("--verbose");
    finalArgs.push("--format", "json");
    const result = await this.execute(this.binary, finalArgs, {
      timeoutMs: options.timeoutMs ?? this.timeoutMs,
      cwd: options.cwd
    });
    if (result.code !== 0) {
      throw new ControllerError("DWS_FAILED", "DWS command failed", { exitCode: result.code });
    }
    const response = parseJson(result.stdout, "dws");
    if (response?.success === false || response?.result?.success === false) {
      throw new ControllerError("DWS_REMOTE_FAILED", "DWS returned an explicit failure response");
    }
    return response;
  }

  searchCommands({ conversationId, start, end, cursor = "0", limit = 100 }) {
    return this.invoke([
      "chat", "message", "search-advanced",
      "--query", "/codex",
      "--conversation-ids", conversationId,
      "--start", start,
      "--end", end,
      "--limit", String(limit),
      "--cursor", String(cursor)
    ]);
  }

  getSelf() {
    return this.invoke(["contact", "user", "get-self"]);
  }

  searchPersonByName(name) {
    return this.invoke(["aisearch", "person", "--keyword", name, "--dimension", "name"]);
  }

  replyMessage({ conversationId, referenceMessageId, referenceSenderOpenDingTalkId, text, uuid }, options = {}) {
    return this.invoke([
      "chat", "message", "reply",
      "--conversation-id", conversationId,
      "--ref-msg-id", referenceMessageId,
      "--ref-sender", referenceSenderOpenDingTalkId,
      "--text", text,
      "--uuid", uuid,
      "--yes"
    ], options);
  }
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

export async function resolveCurrentDwsIdentity(client) {
  const selfResponse = await client.getSelf();
  const selfRecords = asArray(selfResponse?.result ?? selfResponse?.data);
  if (selfRecords.length !== 1) {
    throw new ControllerError("DWS_SELF_IDENTITY_AMBIGUOUS", "DWS current-user response was not unique");
  }
  const selfRecord = selfRecords[0];
  const name = personName(selfRecord);
  const userId = selfRecord?.userId ?? selfRecord?.orgEmployeeModel?.userId;
  if (!name || !userId) {
    throw new ControllerError("DWS_SELF_IDENTITY_INCOMPLETE", "DWS current-user identity is incomplete");
  }

  const personResponse = await client.searchPersonByName(name);
  const candidates = asArray(personResponse?.result?.items ?? personResponse?.result ?? personResponse?.items);
  const exact = candidates.filter((candidate) => personName(candidate) === name);
  if (exact.length !== 1) {
    throw new ControllerError("DWS_SELF_LOOKUP_AMBIGUOUS", "Exact current-user person lookup was not unique");
  }
  const candidate = exact[0];
  const candidateUserId = candidate?.userId ?? candidate?.orgEmployeeModel?.userId;
  const openDingTalkId = candidate?.openDingTalkId ?? candidate?.openDingtalkId
    ?? candidate?.orgEmployeeModel?.openDingTalkId;
  if (!candidateUserId || !openDingTalkId || String(candidateUserId) !== String(userId)) {
    throw new ControllerError("DWS_SELF_IDENTITY_INCOMPLETE", "DWS current-user dual identity could not be verified");
  }
  return { userId: String(userId), openDingTalkId: String(openDingTalkId) };
}

export async function verifyCurrentDwsIdentity(client, channel) {
  const identity = await resolveCurrentDwsIdentity(client);
  if (identity.userId !== channel.selfUserId || identity.openDingTalkId !== channel.selfOpenDingTalkId) {
    throw new ControllerError("DWS_SESSION_IDENTITY_MISMATCH", "Current DWS account does not match enrolled self identity");
  }
  return { verified: true };
}

export function extractPage(response) {
  if (!response || typeof response !== "object") {
    throw new ControllerError("DWS_PAGE_SHAPE", "DWS page is not an object");
  }
  if (response.success === false || response?.result?.success === false) {
    throw new ControllerError("DWS_REMOTE_FAILED", "DWS returned an explicit failure response");
  }
  const result = response?.result ?? response;
  const candidates = [result?.items, result?.messages, result?.list, result?.data, response?.items];
  let items = candidates.find(Array.isArray);
  if (!items && Array.isArray(result?.conversationMessagesList)) {
    items = result.conversationMessagesList.flatMap((conversation) => {
      if (!conversation || typeof conversation !== "object" || !Array.isArray(conversation.messages)) {
        throw new ControllerError("DWS_PAGE_SHAPE", "DWS conversation message group is malformed");
      }
      return conversation.messages.map((message) => {
        if (!message || typeof message !== "object") {
          throw new ControllerError("DWS_PAGE_SHAPE", "DWS conversation message is malformed");
        }
        if (message.openConversationId || !conversation.openConversationId) return message;
        return { ...message, openConversationId: conversation.openConversationId };
      });
    });
  }
  const hasMoreValue = result?.hasMore ?? result?.has_more ?? response?.hasMore;
  if (!items && hasMoreValue === false) items = [];
  if (!items) {
    throw new ControllerError("DWS_PAGE_SHAPE", "DWS page does not contain a message array");
  }
  const nextCursor = result?.nextCursor ?? result?.next_cursor ?? response?.nextCursor ?? null;
  if (hasMoreValue !== undefined && typeof hasMoreValue !== "boolean") {
    throw new ControllerError("DWS_PAGE_SHAPE", "DWS hasMore field is not boolean");
  }
  const normalizedCursor = nextCursor === "" ? null : nextCursor;
  const hasMore = hasMoreValue ?? normalizedCursor !== null;
  return { items, nextCursor: normalizedCursor, hasMore };
}

export async function drainCommandPages(client, request, options = {}) {
  const maxPages = options.maxPages ?? 100;
  const seenCursors = new Set();
  const items = [];
  let cursor = request.cursor ?? "0";

  for (let page = 0; page < maxPages; page += 1) {
    if (seenCursors.has(cursor)) {
      throw new ControllerError("POLL_CURSOR_LOOP", "DWS returned a repeated cursor");
    }
    seenCursors.add(cursor);
    const response = await client.searchCommands({ ...request, cursor });
    const extracted = extractPage(response);
    items.push(...extracted.items);
    if (!extracted.hasMore) return { items, pages: page + 1, complete: true };
    if (extracted.nextCursor === null || extracted.nextCursor === undefined) {
      throw new ControllerError("POLL_CURSOR_MISSING", "DWS indicated more results without a cursor");
    }
    cursor = String(extracted.nextCursor);
  }
  throw new ControllerError("POLL_PAGE_LIMIT", "DWS scan exceeded the page safety limit");
}
