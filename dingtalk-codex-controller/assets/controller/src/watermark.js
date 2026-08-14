import path from "node:path";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { runProcess } from "./dws-client.js";
import { parseJson } from "./util.js";
import { ControllerError } from "./errors.js";

const codexHome = process.env.CODEX_HOME ?? path.join(
  process.env.USERPROFILE ?? process.env.HOME ?? "",
  ".codex"
);
const SKILL_ROOT = process.env.DINGTALK_CHAT_ASSISTANT_SKILL_ROOT ?? path.join(
  codexHome,
  "skills",
  "dingtalk-chat-assistant"
);

export async function prepareGeneratedText(text, options = {}) {
  const skillRoot = options.skillRoot ?? SKILL_ROOT;
  const execute = options.execute ?? runProcess;
  const directory = await mkdtemp(path.join(tmpdir(), "dingtalk-controller-"));
  const source = path.join(directory, "source.txt");
  const final = path.join(directory, "final.txt");
  try {
    await writeFile(source, text, "utf8");
    const watermark = await execute("python", [
      path.join(skillRoot, "scripts", "apply_watermark.py"),
      "--input", source,
      "--output", final,
      "--mode", "generated"
    ], { timeoutMs: 30_000 });
    if (watermark.code !== 0) throw new ControllerError("WATERMARK_FAILED", "Watermark script failed");
    const metricsResult = await execute("python", [
      path.join(skillRoot, "scripts", "message_metrics.py"),
      "--file", final,
      "--limit", String(options.limit ?? 500)
    ], { timeoutMs: 30_000 });
    if (metricsResult.code !== 0) throw new ControllerError("METRICS_FAILED", "Message metrics script failed");
    const finalText = await readFile(final, "utf8");
    return { text: finalText, metrics: parseJson(metricsResult.stdout, "message_metrics.py") };
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
