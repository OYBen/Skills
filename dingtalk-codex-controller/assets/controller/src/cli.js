#!/usr/bin/env node
import path from "node:path";
import { mkdir, readFile } from "node:fs/promises";
import { loadConfig, evaluateGates } from "./config.js";
import { DwsClient, verifyCurrentDwsIdentity } from "./dws-client.js";
import { Store } from "./store.js";
import { scanOnce } from "./scanner.js";
import { doctor } from "./doctor.js";
import { CodexAppServerClient } from "./codex-client.js";
import { jsonOutput, sha256 } from "./util.js";
import { publicError } from "./errors.js";
import { runControllerService } from "./service.js";
import { acquireControllerLease } from "./lease.js";

function parseArgs(argv) {
  const [command = "help", ...rest] = argv.slice(2);
  const options = {};
  if (command === "--help" || command === "-h") return { command: "help", options: { help: true } };
  for (let index = 0; index < rest.length; index += 1) {
    const value = rest[index];
    if (value === "--config") options.configPath = rest[++index];
    else if (value === "--fixture") options.fixturePath = rest[++index];
    else if (value === "--help" || value === "-h") options.help = true;
    else throw new Error(`Unknown option: ${value}`);
  }
  return { command, options };
}

function usage() {
  return `Usage:
  node src/cli.js doctor [--config config/config.json]
  node src/cli.js hash-actions [--config config/config.example.json]
  node src/cli.js probe-dws [--config config/config.json]
  node src/cli.js probe-codex [--config config/config.json]
  node src/cli.js scan-once --config config/config.json
  node src/cli.js serve --config config/config.json
  node src/cli.js scan-fixture --config <config> --fixture <response.json>

Safety: observe mode has no outbound effects. Active mode can reply and call
turn/start only after its strict configuration and all four gates validate.`;
}

async function probeDws(configPath) {
  const client = new DwsClient();
  const self = await client.getSelf();
  const serialized = JSON.stringify(self);
  const selfName = self?.result?.[0]?.orgEmployeeModel?.orgUserName
    ?? self?.result?.orgEmployeeModel?.orgUserName
    ?? null;
  const fieldPresence = {
    userId: /"userId"\s*:/u.test(serialized),
    openDingTalkId: /"openDingTalkId"\s*:/iu.test(serialized),
    organization: /"orgName"\s*:/u.test(serialized)
  };
  let exactPersonLookup = { attempted: false };
  if (selfName) {
    const people = await client.searchPersonByName(selfName);
    const candidates = people?.result?.items ?? people?.result ?? people?.items ?? [];
    const list = Array.isArray(candidates) ? candidates : [];
    const exact = list.filter((candidate) => {
      const name = candidate.name ?? candidate.userName ?? candidate.orgUserName
        ?? candidate.orgEmployeeModel?.orgUserName ?? candidate.meta?.name
        ?? candidate.title ?? candidate.author;
      return name === selfName;
    });
    const exactSerialized = JSON.stringify(exact);
    exactPersonLookup = {
      attempted: true,
      exactCandidateCount: exact.length,
      userIdPresent: /"userId"\s*:/u.test(exactSerialized),
      openDingTalkIdPresent: /"openDingTalkId"\s*:/iu.test(exactSerialized)
    };
  }
  let scopedSearch = { attempted: false };
  if (configPath) {
    const config = await loadConfig(configPath);
    const end = new Date(Date.now() - (config.closedWindowDelaySeconds ?? 10) * 1000);
    const start = new Date(end.getTime() - 5 * 60_000);
    const response = await client.searchCommands({
      conversationId: config.channel.conversationId,
      start: start.toISOString(),
      end: end.toISOString(),
      cursor: "0",
      limit: 1
    });
    const result = response?.result ?? response;
    scopedSearch = {
      attempted: true,
      success: response?.success !== false,
      topLevelKeys: Object.keys(response).sort(),
      resultKeys: result && typeof result === "object" ? Object.keys(result).sort() : [],
      itemCount: Array.isArray(result?.items) ? result.items.length : null,
      hasMoreField: Object.hasOwn(result ?? {}, "hasMore"),
      nextCursorField: Object.hasOwn(result ?? {}, "nextCursor")
    };
  }
  return {
    schemaVersion: "dingtalk-controller.dws-probe.v1",
    status: fieldPresence.userId &&
      (fieldPresence.openDingTalkId || (exactPersonLookup.exactCandidateCount === 1 && exactPersonLookup.openDingTalkIdPresent))
      ? "IDENTITY_FIELDS_READY" : "IDENTITY_FIELDS_INCOMPLETE",
    selfFieldPresence: fieldPresence,
    exactPersonLookup,
    scopedSearch,
    privacy: "Values and message bodies intentionally omitted"
  };
}

async function probeCodex(configPath) {
  let config = null;
  if (configPath) config = await loadConfig(configPath);
  const cwd = config?.task?.cwd ?? path.resolve("sandbox");
  const client = new CodexAppServerClient({ cwd, timeoutMs: 30_000 });
  try {
    await client.start();
    const profiles = await client.listPermissionProfiles(cwd);
    let thread = null;
    if (config?.task?.threadId) thread = await client.readThread(config.task.threadId, false);
    const profileItems = profiles?.profiles ?? profiles?.items ?? profiles?.data ?? [];
    return {
      schemaVersion: "dingtalk-controller.codex-probe.v1",
      status: "READ_ONLY_OK",
      permissionProfiles: Array.isArray(profileItems)
        ? profileItems.map((item) => ({ id: item.id ?? item.name ?? null, allowed: item.allowed ?? item.isAllowed ?? null }))
        : [],
      thread: thread ? {
        idMatches: (thread.thread?.id ?? thread.id) === config.task.threadId,
        status: thread.thread?.status ?? thread.status ?? null,
        titleMatches: config.task.expectedTitle
          ? (thread.thread?.name ?? thread.thread?.title ?? thread.name ?? thread.title) === config.task.expectedTitle
          : null
      } : null,
      safety: { turnStarted: false, threadResumed: false }
    };
  } finally {
    await client.stop();
  }
}

async function main() {
  const { command, options } = parseArgs(process.argv);
  if (options.help || command === "help") {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  if (command === "doctor") {
    jsonOutput(await doctor({ configPath: options.configPath }));
    return;
  }
  if (command === "hash-actions") {
    const config = await loadConfig(options.configPath ?? "config/config.example.json", { requireEnrollment: false, verifyActions: false });
    const hashes = {};
    for (const [alias, action] of Object.entries(config.actions)) hashes[alias] = sha256(await readFile(action.promptPath));
    jsonOutput({ hashes });
    return;
  }
  if (command === "probe-dws") {
    jsonOutput(await probeDws(options.configPath));
    return;
  }
  if (command === "probe-codex") {
    jsonOutput(await probeCodex(options.configPath));
    return;
  }
  if (command === "scan-once") {
    if (!options.configPath) throw new Error("scan-once requires --config");
    const result = await runControllerService({
      configPath: options.configPath,
      once: true,
      onResult: (scan) => jsonOutput({ event: "scan", ...scan })
    });
    jsonOutput({ event: "stopped", ...result });
    return;
  }
  if (command === "serve") {
    if (!options.configPath) throw new Error("serve requires --config");
    const controller = new AbortController();
    const stop = () => controller.abort();
    const stopFromMessage = (message) => {
      if (message?.type === "shutdown") stop();
    };
    process.once("SIGINT", stop);
    process.once("SIGTERM", stop);
    process.once("disconnect", stop);
    process.on("message", stopFromMessage);
    try {
      const result = await runControllerService({
        configPath: options.configPath,
        signal: controller.signal,
        onResult: (scan) => jsonOutput({ event: "scan", ...scan })
      });
      jsonOutput({ event: "stopped", ...result });
    } finally {
      process.removeListener("disconnect", stop);
      process.removeListener("message", stopFromMessage);
      if (process.connected) process.disconnect();
    }
    return;
  }
  if (command === "scan-fixture") {
    if (!options.configPath || !options.fixturePath) throw new Error("scan-fixture requires --config and --fixture");
    const config = await loadConfig(options.configPath);
    const fixture = JSON.parse(await readFile(options.fixturePath, "utf8"));
    const fake = { searchCommands: async () => fixture };
    const store = new Store(":memory:");
    try { jsonOutput(await scanOnce({ config, store, dwsClient: fake })); }
    finally { store.close(); }
    return;
  }
  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  jsonOutput({ status: "ERROR", error: publicError(error) });
  process.exitCode = 1;
});
