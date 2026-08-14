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
let trustedIdentity;
try {
  trustedIdentity = JSON.parse(await readFile(path.join(
    skillRoot,
    "references",
    "trusted-recipient.local.json"
  ), "utf8"));
} catch (error) {
  if (error.code !== "ENOENT") throw error;
  const deliveryPolicy = await readFile(path.join(
    skillRoot,
    "references",
    "delivery-policy.md"
  ), "utf8");
  trustedIdentity = {
    userId: deliveryPolicy.match(/`userId`：`([^`]+)`/u)?.[1],
    openDingTalkId: deliveryPolicy.match(/`openDingTalkId`：`([^`]+)`/u)?.[1]
  };
}

export const trustedUserId = trustedIdentity.userId;
export const trustedOpenDingTalkId = trustedIdentity.openDingTalkId;
if (!trustedUserId || !trustedOpenDingTalkId) {
  throw new Error("Trusted identity fixture is unavailable");
}
