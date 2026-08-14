import { sha256 } from "./util.js";

export const TRUSTED_RECIPIENT_NAME = "欧阳斌";

const TRUSTED_USER_ID_SHA256 = "f6a69b7eaaf63b9e1c45c17c21eb6f8da8bbd5658b56a97d184721855a7cf444";
const TRUSTED_OPEN_DINGTALK_ID_SHA256 = "66ad17f9af6e2b31ec62a7f95e790432ce058a1b0566a084d089f9f3aecda1ee";

export function matchesTrustedRecipient(userId, openDingTalkId) {
  return sha256(String(userId ?? "")) === TRUSTED_USER_ID_SHA256 &&
    sha256(String(openDingTalkId ?? "")) === TRUSTED_OPEN_DINGTALK_ID_SHA256;
}
