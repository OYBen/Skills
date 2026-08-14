import { access } from "node:fs/promises";
import { constants } from "node:fs";
import { evaluateGates, loadConfig } from "./config.js";
import { runProcess } from "./dws-client.js";
import { Store } from "./store.js";
import { DesktopIpcClient } from "./codex-client.js";
import { listAllThreads } from "./thread-directory.js";

async function executableVersion(binary, args) {
  try {
    const result = await runProcess(binary, args, { timeoutMs: 10_000 });
    return { available: result.code === 0, exitCode: result.code, versionObserved: (result.stdout || result.stderr).trim().slice(0, 200) };
  } catch (error) {
    return { available: false, error: error.code ?? error.message };
  }
}

export function doctorSafety(config, gates, ready) {
  const activeEnabled = Boolean(ready && gates?.runEnabled);
  return {
    status: activeEnabled ? "ACTIVE_READY" : ready ? "OBSERVE_READY" : "NOT_READY",
    safety: {
      sendsEnabled: activeEnabled,
      turnsEnabled: activeEnabled,
      reason: activeEnabled
        ? "Active service is reachable under the validated configuration gates"
        : config?.task?.enrolled === false
          ? "Polling only; no Codex task is enrolled"
          : "Observe mode or at least one active gate is closed"
    }
  };
}

export async function doctor(options = {}) {
  const configPath = options.configPath;
  let config = null;
  let configError = null;
  if (configPath) {
    try { config = await loadConfig(configPath); }
    catch (error) { configError = { code: error.code ?? "CONFIG_ERROR", message: error.message }; }
  }

  const node = { version: process.version, sqlite: true };
  const dws = await executableVersion("dws", ["version", "--format", "json"]);
  const codexBinary = process.env.CODEX_BIN ?? "codex";
  const codex = await executableVersion(codexBinary, ["--version"]);
  let desktop = null;
  let desktopClient;
  try {
    const threads = await listAllThreads(options.threadDirectory);
    desktopClient = options.desktopClient ?? new DesktopIpcClient({ timeoutMs: 5_000 });
    await desktopClient.start();
    desktop = { ipcAvailable: true, taskDirectoryAvailable: true, taskCount: threads.length };
  } catch (error) {
    desktop = {
      ipcAvailable: false,
      taskDirectoryAvailable: false,
      error: error.code ?? error.message
    };
  } finally {
    if (!options.desktopClient) await desktopClient?.stop();
  }
  let storage = null;
  if (config) {
    try {
      await access(config.task?.cwd ?? config.projectRoot, constants.R_OK);
      const store = new Store(config.paths.database);
      storage = { available: true, ...store.health() };
      store.close();
    } catch (error) {
      storage = { available: false, error: error.code ?? error.message };
    }
  }
  const gates = config ? evaluateGates(config) : null;
  const ready = Boolean(config && !configError && dws.available && codex.available &&
    desktop.ipcAvailable && desktop.taskDirectoryAvailable && storage?.available);
  const availability = doctorSafety(config, gates, ready);
  return {
    schemaVersion: "dingtalk-controller.doctor.v1",
    status: availability.status,
    config: config ? { loaded: true, mode: config.mode } : { loaded: false, error: configError },
    task: config ? { enrolled: config.task?.enrolled !== false && Boolean(config.task?.threadId) } : null,
    node,
    dws,
    codex: { ...codex, binarySource: process.env.CODEX_BIN ? "CODEX_BIN" : "PATH" },
    desktop,
    storage,
    gates,
    safety: availability.safety
  };
}
