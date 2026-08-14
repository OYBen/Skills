import { createHash, randomUUID } from "node:crypto";
import { mkdir, open, rename, readFile } from "node:fs/promises";
import path from "node:path";

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function hashIdentifier(value) {
  return sha256(`dingtalk-controller:v1:${String(value)}`);
}

export function codePointLength(value) {
  return Array.from(value).length;
}

export function isoNow(clock = () => new Date()) {
  return clock().toISOString();
}

export function newRequestId(clock = () => new Date()) {
  const stamp = clock().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  return `REQ-${stamp}-${randomUUID().slice(0, 8)}`;
}

export function parseJson(text, source = "JSON") {
  try {
    return JSON.parse(text);
  } catch (error) {
    const wrapped = new Error(`${source} returned invalid JSON`);
    wrapped.cause = error;
    throw wrapped;
  }
}

export async function writeFileAtomic(filePath, content) {
  const directory = path.dirname(filePath);
  await mkdir(directory, { recursive: true });
  const temporary = `${filePath}.${randomUUID()}.tmp`;
  const handle = await open(temporary, "wx", 0o600);
  try {
    await handle.writeFile(content, { encoding: "utf8" });
    await handle.sync();
  } finally {
    await handle.close();
  }
  await rename(temporary, filePath);
}

export async function readUtf8(filePath) {
  return readFile(filePath, "utf8");
}

export function jsonOutput(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}
