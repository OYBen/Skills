import path from "node:path";
import { mkdir } from "node:fs/promises";
import { loadConfig, evaluateGates } from "./config.js";
import { DwsClient, verifyCurrentDwsIdentity } from "./dws-client.js";
import { Store } from "./store.js";
import { scanOnce } from "./scanner.js";
import { acquireControllerLease } from "./lease.js";
import { publicError } from "./errors.js";
import { CodexAppServerClient, DesktopIpcClient } from "./codex-client.js";
import { advanceController } from "./controller-workflow.js";

const wait = (milliseconds, signal) => new Promise((resolve) => {
  if (signal?.aborted) return resolve();
  const timer = setTimeout(resolve, milliseconds);
  signal?.addEventListener("abort", () => {
    clearTimeout(timer);
    resolve();
  }, { once: true });
});

export async function runObserveService(options) {
  const config = await loadConfig(options.configPath);
  if (config.mode !== "observe") {
    throw new Error("This implementation rejects active service mode");
  }
  const gates = evaluateGates(config);
  if (!gates.observeOnly) throw new Error("Observe-mode gate evaluation failed");
  await mkdir(path.dirname(config.paths.database), { recursive: true });
  const store = new Store(config.paths.database);
  let lease;
  const client = options.dwsClient ?? new DwsClient();
  const signal = options.signal;
  const onResult = options.onResult ?? (() => {});
  let scans = 0;
  try {
    lease = acquireControllerLease(store, { ttlSeconds: config.limits?.controllerLeaseSeconds ?? 60 });
    do {
      lease.assertHeld();
      await verifyCurrentDwsIdentity(client, config.channel);
      let result;
      try {
        result = await scanOnce({
          config, store, dwsClient: client,
          assertLease: () => lease.assertHeld(),
          leaseTransaction: (callback) => lease.transaction(callback)
        });
      } catch (error) {
        result = { status: "ERROR", error: publicError(error) };
      }
      scans += 1;
      onResult(result);
      if (options.once || signal?.aborted) break;
      await wait(config.pollIntervalSeconds * 1000, signal);
    } while (!signal?.aborted);
    return { scans, health: store.health() };
  } finally {
    lease?.release();
    store.close();
  }
}

export async function runControllerService(options) {
  const config = await loadConfig(options.configPath);
  if (config.mode === "observe") return runObserveService(options);
  if (config.mode !== "active") throw new Error("Controller service mode is invalid");
  const gates = evaluateGates(config);
  if (!gates.runEnabled) throw new Error("Active controller gates are not all open");
  await mkdir(path.dirname(config.paths.database), { recursive: true });
  const store = new Store(config.paths.database);
  const dwsClient = options.dwsClient ?? new DwsClient();
  const desktopClient = options.desktopClient ?? new DesktopIpcClient({ timeoutMs: 15_000 });
  const threadDirectory = options.threadDirectory ?? null;
  let codexClient = options.codexClient ?? null;
  const signal = options.signal;
  const onResult = options.onResult ?? (() => {});
  let lease;
  let scans = 0;
  let ownsCodexClient = false;
  const getCodexClient = async () => {
    if (codexClient) return codexClient;
    codexClient = new CodexAppServerClient({ cwd: config.task.cwd, timeoutMs: 30_000 });
    ownsCodexClient = true;
    await codexClient.start();
    return codexClient;
  };
  try {
    lease = acquireControllerLease(store, { ttlSeconds: config.limits?.controllerLeaseSeconds ?? 60 });
    lease.transaction(() => store.recoverInFlightStates());
    do {
      lease.assertHeld();
      await verifyCurrentDwsIdentity(dwsClient, config.channel);
      let scan;
      try {
        scan = await scanOnce({
          config, store, dwsClient,
          assertLease: () => lease.assertHeld(),
          leaseTransaction: (callback) => lease.transaction(callback)
        });
      } catch (error) {
        scan = { status: "ERROR", error: publicError(error) };
      }
      scans += 1;
      let workflow = [];
      if (scan.status === "COMPLETE") {
        workflow = await advanceController({
          config, gates, store, dwsClient, codexClient, desktopClient, threadDirectory, getCodexClient,
          assertLease: () => lease.assertHeld(),
          leaseTransaction: (callback) => lease.transaction(callback)
        });
      }
      onResult({ ...scan, workflow });
      if (options.once || signal?.aborted) break;
      await wait(config.pollIntervalSeconds * 1000, signal);
    } while (!signal?.aborted);
    return { scans, health: store.health() };
  } finally {
    if (ownsCodexClient) await codexClient?.stop();
    if (!options.desktopClient) await desktopClient.stop();
    lease?.release();
    store.close();
  }
}
