import { spawn } from "node:child_process";
import net from "node:net";
import readline from "node:readline";
import { randomUUID } from "node:crypto";
import { ControllerError } from "./errors.js";

const DEFAULT_DESKTOP_PIPE = "\\\\.\\pipe\\codex-ipc";
const MAX_IPC_FRAME_BYTES = 256 * 1024 * 1024;
const IPC_METHOD_VERSIONS = new Map([
  ["initialize", 0],
  ["thread-owner-discovery", 1],
  ["thread-follower-start-turn", 1]
]);

function desktopErrorCode(error) {
  if (error === "no-client-found" || error === "client-not-found" || error === "client-disconnected") {
    return "DESKTOP_THREAD_OWNER_UNAVAILABLE";
  }
  if (error === "request-timeout" || error === "timeout") return "DESKTOP_IPC_TIMEOUT";
  if (error === "request-version-mismatch") return "DESKTOP_IPC_VERSION_MISMATCH";
  return "DESKTOP_IPC_ERROR";
}

function encodeIpcFrame(message) {
  const json = JSON.stringify(message);
  const byteLength = Buffer.byteLength(json, "utf8");
  if (byteLength === 0 || byteLength > MAX_IPC_FRAME_BYTES) {
    throw new ControllerError("DESKTOP_IPC_FRAME_INVALID", "Desktop IPC frame size is invalid");
  }
  const frame = Buffer.allocUnsafe(4 + byteLength);
  frame.writeUInt32LE(byteLength, 0);
  frame.write(json, 4, "utf8");
  return frame;
}

export function extractDesktopTurnId(response) {
  let current = response;
  for (let depth = 0; depth < 6 && current && typeof current === "object"; depth += 1) {
    if (typeof current.turn?.id === "string" && current.turn.id) return current.turn.id;
    current = current.result;
  }
  return null;
}

export class DesktopIpcClient {
  constructor(options = {}) {
    this.pipePath = options.pipePath ?? DEFAULT_DESKTOP_PIPE;
    this.clientType = options.clientType ?? "dingtalk-controller";
    this.timeoutMs = options.timeoutMs ?? 15_000;
    this.pending = new Map();
    this.clientId = null;
    this.buffer = Buffer.alloc(0);
  }

  async start() {
    if (this.socket?.writable && this.clientId) return;
    if (this.startPromise) return this.startPromise;
    this.startPromise = this.connectAndInitialize();
    try {
      await this.startPromise;
    } finally {
      this.startPromise = null;
    }
  }

  async connectAndInitialize() {
    const socket = net.createConnection(this.pipePath);
    this.socket = socket;
    this.buffer = Buffer.alloc(0);
    socket.on("data", (chunk) => this.handleData(chunk));
    socket.on("error", (error) => this.handleSocketFailure(error));
    socket.on("close", () => this.handleSocketFailure(
      new ControllerError("DESKTOP_IPC_CLOSED", "Desktop IPC connection closed")
    ));

    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new ControllerError("DESKTOP_IPC_CONNECT_TIMEOUT", "Timed out connecting to Codex Desktop"));
        socket.destroy();
      }, this.timeoutMs);
      socket.once("connect", () => {
        clearTimeout(timer);
        resolve();
      });
      socket.once("error", (error) => {
        clearTimeout(timer);
        reject(new ControllerError("DESKTOP_IPC_UNAVAILABLE", "Codex Desktop IPC is unavailable", {
          cause: error.code ?? error.message
        }));
      });
    });

    const response = await this.requestRaw("initialize", { clientType: this.clientType }, {
      timeoutMs: this.timeoutMs,
      version: 0
    });
    const clientId = response?.result?.clientId;
    if (typeof clientId !== "string" || !clientId) {
      this.closeSocket();
      throw new ControllerError("DESKTOP_IPC_INITIALIZE_INVALID", "Codex Desktop returned an invalid IPC client identity");
    }
    this.clientId = clientId;
  }

  handleData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (this.buffer.length >= 4) {
      const frameLength = this.buffer.readUInt32LE(0);
      if (frameLength === 0 || frameLength > MAX_IPC_FRAME_BYTES) {
        this.handleSocketFailure(new ControllerError("DESKTOP_IPC_FRAME_INVALID", "Desktop IPC frame size is invalid"));
        this.closeSocket();
        return;
      }
      if (this.buffer.length < frameLength + 4) return;
      const body = this.buffer.subarray(4, frameLength + 4).toString("utf8");
      this.buffer = this.buffer.subarray(frameLength + 4);
      let message;
      try {
        message = JSON.parse(body);
      } catch {
        this.handleSocketFailure(new ControllerError("DESKTOP_IPC_JSON_INVALID", "Desktop IPC returned invalid JSON"));
        this.closeSocket();
        return;
      }
      if (message.type !== "response" || !this.pending.has(message.requestId)) continue;
      const pending = this.pending.get(message.requestId);
      this.pending.delete(message.requestId);
      clearTimeout(pending.timer);
      if (message.resultType === "error") {
        pending.reject(new ControllerError(desktopErrorCode(message.error), "Codex Desktop IPC request failed", {
          desktopError: message.error,
          method: pending.method
        }));
      } else {
        pending.resolve(message);
      }
    }
  }

  handleSocketFailure(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error instanceof ControllerError
        ? error
        : new ControllerError("DESKTOP_IPC_CONNECTION_FAILED", "Codex Desktop IPC connection failed", {
          cause: error.code ?? error.message
        }));
    }
    this.pending.clear();
    this.clientId = null;
  }

  requestRaw(method, params, options = {}) {
    if (!this.socket?.writable) {
      return Promise.reject(new ControllerError("DESKTOP_IPC_NOT_CONNECTED", "Codex Desktop IPC is not connected"));
    }
    const requestId = randomUUID();
    const timeoutMs = options.timeoutMs ?? this.timeoutMs;
    const message = {
      type: "request",
      requestId,
      version: options.version ?? IPC_METHOD_VERSIONS.get(method) ?? 0,
      method,
      params
    };
    if (this.clientId) message.sourceClientId = this.clientId;
    if (options.targetClientId) message.targetClientId = options.targetClientId;
    if (timeoutMs != null) message.timeoutMs = timeoutMs;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new ControllerError("DESKTOP_IPC_TIMEOUT", `Timed out waiting for ${method}`));
      }, timeoutMs);
      this.pending.set(requestId, { resolve, reject, timer, method });
      try {
        this.socket.write(encodeIpcFrame(message));
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(requestId);
        reject(error);
      }
    });
  }

  async findThreadOwner(threadId, options = {}) {
    await this.start();
    try {
      const response = await this.requestRaw("thread-owner-discovery", {
        hostId: options.hostId ?? "local",
        conversationId: threadId
      }, { timeoutMs: options.timeoutMs ?? this.timeoutMs, version: 1 });
      return typeof response.handledByClientId === "string" ? response.handledByClientId : null;
    } catch (error) {
      if (error?.code === "DESKTOP_THREAD_OWNER_UNAVAILABLE") return null;
      throw error;
    }
  }

  async startThreadTurn(threadId, text, options = {}) {
    await this.start();
    const ownerClientId = options.ownerClientId ?? await this.findThreadOwner(threadId, options);
    if (!ownerClientId) {
      throw new ControllerError("DESKTOP_THREAD_OWNER_UNAVAILABLE", "The target task is not owned by a live Codex Desktop window");
    }
    const response = await this.requestRaw("thread-follower-start-turn", {
      conversationId: threadId,
      turnStartParams: {
        input: [{ type: "text", text, text_elements: [] }],
        clientUserMessageId: options.clientUserMessageId ?? randomUUID()
      },
      mcpAppModelContextAttachments: []
    }, {
      targetClientId: ownerClientId,
      timeoutMs: options.timeoutMs ?? this.timeoutMs,
      version: 1
    });
    const turnId = extractDesktopTurnId(response);
    if (!turnId) {
      throw new ControllerError("TURN_ID_MISSING", "Codex Desktop accepted no identifiable turn", {
        handledByClientId: response.handledByClientId ?? null
      });
    }
    return { turn: { id: turnId }, handledByClientId: response.handledByClientId ?? ownerClientId };
  }

  closeSocket() {
    const socket = this.socket;
    this.socket = null;
    this.clientId = null;
    if (socket && !socket.destroyed) socket.destroy();
  }

  async stop() {
    this.handleSocketFailure(new ControllerError("DESKTOP_IPC_STOPPED", "Desktop IPC client stopped"));
    this.closeSocket();
  }
}

export class CodexAppServerClient {
  constructor(options = {}) {
    this.binary = options.binary ?? process.env.CODEX_BIN ?? "codex";
    this.cwd = options.cwd;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.experimentalApi = options.experimentalApi ?? true;
    this.nextId = 1;
    this.pending = new Map();
    this.notifications = [];
  }

  async start() {
    if (this.process) return;
    this.process = spawn(this.binary, ["app-server", "--listen", "stdio://"], {
      cwd: this.cwd,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
      shell: false
    });
    this.stderr = "";
    this.process.stderr.on("data", (chunk) => { this.stderr += chunk; });
    this.process.once("error", (error) => this.rejectAll(error));
    const lines = readline.createInterface({ input: this.process.stdout });
    lines.on("line", (line) => this.handleLine(line));
    await this.request("initialize", {
      clientInfo: { name: "dingtalk-controller", title: "DingTalk Controller", version: "0.1.0" },
      capabilities: { experimentalApi: this.experimentalApi }
    });
    this.notify("initialized", {});
  }

  handleLine(line) {
    let message;
    try { message = JSON.parse(line); } catch { return; }
    if (message.id !== undefined && this.pending.has(message.id)) {
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(new ControllerError("CODEX_RPC_ERROR", "Codex App Server returned an error", message.error));
      else pending.resolve(message.result);
      return;
    }
    if (message.method) this.notifications.push(message);
  }

  rejectAll(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  request(method, params = {}) {
    if (!this.process?.stdin?.writable) {
      return Promise.reject(new ControllerError("CODEX_NOT_STARTED", "Codex App Server is not running"));
    }
    const id = this.nextId++;
    this.process.stdin.write(`${JSON.stringify({ method, id, params })}\n`);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new ControllerError("CODEX_RPC_TIMEOUT", `Timed out waiting for ${method}`));
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
    });
  }

  notify(method, params = {}) {
    this.process.stdin.write(`${JSON.stringify({ method, params })}\n`);
  }

  listPermissionProfiles(cwd = this.cwd) {
    return this.request("permissionProfile/list", { cwd, limit: 100 });
  }

  listThreads(options = {}) {
    const params = {
      limit: options.limit ?? 100,
      archived: options.archived ?? false,
      sourceKinds: options.sourceKinds,
      sortKey: options.sortKey ?? "updated_at",
      sortDirection: options.sortDirection ?? "desc"
    };
    if (options.cursor) params.cursor = options.cursor;
    return this.request("thread/list", params);
  }

  startThread(options = {}) {
    const params = {};
    if (options.cwd) params.cwd = options.cwd;
    if (options.permissionProfile) params.permissions = options.permissionProfile;
    if (options.approvalPolicy) params.approvalPolicy = options.approvalPolicy;
    if (options.developerInstructions) params.developerInstructions = options.developerInstructions;
    return this.request("thread/start", params);
  }

  setThreadName(threadId, name) {
    return this.request("thread/name/set", { threadId, name });
  }

  readThread(threadId, includeTurns = false) {
    return this.request("thread/read", { threadId, includeTurns });
  }

  resumeThread(threadId, overrides = {}) {
    const params = { threadId };
    if (overrides.cwd) params.cwd = overrides.cwd;
    if (overrides.permissionProfile) params.permissions = overrides.permissionProfile;
    if (overrides.approvalPolicy) params.approvalPolicy = overrides.approvalPolicy;
    return this.request("thread/resume", params);
  }

  startTurn(threadId, text, options = {}) {
    const params = { threadId, input: [{ type: "text", text }] };
    if (options.cwd) params.cwd = options.cwd;
    if (options.approvalPolicy) params.approvalPolicy = options.approvalPolicy;
    if (options.permissionProfile) params.permissions = options.permissionProfile;
    if (options.outputSchema) params.outputSchema = options.outputSchema;
    return this.request("turn/start", params);
  }

  async stop() {
    if (!this.process) return;
    this.process.stdin.end();
    this.process.kill();
    this.rejectAll(new ControllerError("CODEX_STOPPED", "Codex App Server stopped"));
    this.process = null;
  }
}
