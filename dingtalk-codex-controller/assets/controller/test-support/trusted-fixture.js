import { readFile } from "node:fs/promises";
import path from "node:path";

const codexHome = process.env.CODEX_HOME ?? path.join(
  process.env.USERPROFILE ?? process.env.HOME ?? "",
  ".codex"
);
const skillRoot = process.env.DINGTALK_CHAT_ASSISTANT_SKILL_ROOT ?? path.join(
  codexHome,
  "skills",
  "dingtalk-chat-assistant"
);
const deliveryPolicy = await readFile(path.join(
  skillRoot,
  "references",
  "delivery-policy.md"
), "utf8");

export const trustedUserId = deliveryPolicy.match(/`userId`：`([^`]+)`/u)?.[1];
export const trustedOpenDingTalkId = deliveryPolicy.match(/`openDingTalkId`：`([^`]+)`/u)?.[1];
if (!trustedUserId || !trustedOpenDingTalkId) {
  throw new Error("Trusted identity fixture is unavailable");
}
