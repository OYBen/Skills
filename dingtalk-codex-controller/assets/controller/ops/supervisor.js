import { closeSync, existsSync, mkdirSync, openSync, readdirSync, rmSync, statSync } from "node:fs";
import path from "node:path";
import { fork } from "node:child_process";
import { fileURLToPath } from "node:url";

const opsDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.dirname(opsDirectory);
const logDirectory = path.join(projectRoot, "logs", "scheduled-task");
const configPath = path.join(projectRoot, "config", "config.json");
const entryPoint = path.join(projectRoot, "src", "cli.js");

function firstExisting(candidates, name) {
  const found = candidates.find((candidate) => candidate && existsSync(candidate));
  if (!found) throw new Error(`Required executable is unavailable: ${name}`);
  return found;
}

function removeExpiredLogs() {
  const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
  for (const name of readdirSync(logDirectory)) {
    const target = path.join(logDirectory, name);
    if (statSync(target).isFile() && statSync(target).mtimeMs < cutoff) rmSync(target, { force: true });
  }
}

mkdirSync(logDirectory, { recursive: true });
removeExpiredLogs();

const localAppData = process.env.LOCALAPPDATA;
const userProfile = process.env.USERPROFILE;
const programFiles = process.env.ProgramFiles ?? "C:\\Program Files";
const nodePath = firstExisting([path.join(programFiles, "nodejs", "node.exe")], "node");
const dwsPath = firstExisting([path.join(userProfile, ".local", "bin", "dws.exe")], "dws");
const codexPath = firstExisting([
  path.join(localAppData, "Programs", "OpenAI", "Codex", "bin", "codex.exe"),
  path.join(localAppData, "OpenAI", "Codex", "bin", "codex.exe"),
  process.env.CODEX_BIN
], "codex");
const pythonPath = firstExisting([
  path.join(localAppData, "Programs", "Python", "Python313", "python.exe")
], "python");

if (!existsSync(configPath) || !existsSync(entryPoint)) throw new Error("Controller files are incomplete");

const executableDirectories = [nodePath, dwsPath, codexPath, pythonPath].map(path.dirname);
const environment = {
  ...process.env,
  CODEX_BIN: codexPath,
  Path: [...new Set([...executableDirectories, process.env.Path].filter(Boolean))].join(path.delimiter)
};
const stamp = new Date().toISOString().replace(/[-:]/gu, "").replace(/\..*$/u, "").replace("T", "-");
const stdoutPath = path.join(logDirectory, `controller-${stamp}-${process.pid}.stdout.log`);
const stderrPath = path.join(logDirectory, `controller-${stamp}-${process.pid}.stderr.log`);
const stdout = openSync(stdoutPath, "a");
const stderr = openSync(stderrPath, "a");

const child = fork(entryPoint, ["serve", "--config", configPath], {
  execPath: nodePath,
  cwd: projectRoot,
  env: environment,
  windowsHide: true,
  stdio: ["ignore", stdout, stderr, "ipc"]
});

let stopping = false;
let forceTimer;
function stop() {
  if (stopping) return;
  stopping = true;
  clearInterval(parentMonitor);
  if (child.connected) child.send({ type: "shutdown", source: "supervisor" });
  else if (!child.killed) child.kill();
  forceTimer = setTimeout(() => {
    if (!child.killed) child.kill();
  }, 10_000);
  forceTimer.unref();
}

function parentIsAlive() {
  try {
    process.kill(process.ppid, 0);
    return true;
  } catch {
    return false;
  }
}

const parentMonitor = setInterval(() => {
  if (!parentIsAlive()) stop();
}, 2_000);
parentMonitor.unref();

process.once("SIGINT", stop);
process.once("SIGTERM", stop);
child.once("error", (error) => {
  clearInterval(parentMonitor);
  clearTimeout(forceTimer);
  closeSync(stdout);
  closeSync(stderr);
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
child.once("exit", (code) => {
  clearInterval(parentMonitor);
  clearTimeout(forceTimer);
  closeSync(stdout);
  closeSync(stderr);
  process.exit(stopping || code === 0 ? 0 : 1);
});
