import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { constants } from "node:fs";
import { ControllerError } from "./errors.js";
import { sha256 } from "./util.js";
import { matchesTrustedRecipient, TRUSTED_RECIPIENT_NAME } from "./trusted-policy.js";

const PLACEHOLDER = /^<.*>$/u;
export const HEALTH_CHECK_PROMPT_SHA256 = "84656e10ba7dde5faacc519247fb149c63b7cf661d8a4a6408691b49d8be0e2d";

function requireString(value, field) {
  if (typeof value !== "string" || !value.trim() || PLACEHOLDER.test(value.trim())) {
    throw new ControllerError("CONFIG_INCOMPLETE", `${field} must be a resolved non-placeholder string`);
  }
  return value;
}

function resolveLocal(baseDirectory, configuredPath) {
  return path.isAbsolute(configuredPath) ? configuredPath : path.resolve(baseDirectory, configuredPath);
}

export async function loadConfig(configPath, options = {}) {
  const absolutePath = path.resolve(configPath);
  let raw;
  try {
    raw = await readFile(absolutePath, "utf8");
  } catch (error) {
    throw new ControllerError("CONFIG_NOT_FOUND", `Configuration file not found: ${absolutePath}`);
  }

  let config;
  try {
    config = JSON.parse(raw);
  } catch {
    throw new ControllerError("CONFIG_INVALID_JSON", "Configuration file is not valid JSON");
  }

  if (config.schemaVersion !== 1) {
    throw new ControllerError("CONFIG_SCHEMA", "Unsupported configuration schema version");
  }
  if (!new Set(["observe", "active"]).has(config.mode)) {
    throw new ControllerError("CONFIG_MODE", "Mode must be observe or active");
  }
  if (!config.channel || !config.paths || !config.gates || !config.delivery) {
    throw new ControllerError("CONFIG_SHAPE", "Configuration is missing required sections");
  }

  const baseDirectory = path.dirname(absolutePath);
  const normalized = structuredClone(config);
  normalized.configPath = absolutePath;
  normalized.baseDirectory = baseDirectory;
  normalized.projectRoot = path.resolve(baseDirectory, "..");
  normalized.paths.database = resolveLocal(normalized.projectRoot, config.paths.database);
  normalized.paths.payloads = resolveLocal(normalized.projectRoot, config.paths.payloads);
  normalized.task = normalized.task ?? { enrolled: false };

  if (options.requireEnrollment !== false) {
    if (!new Set(["direct", "self-chat"]).has(config.channel.kind)) {
      throw new ControllerError("CONFIG_CHANNEL_KIND", "channel.kind must be direct or self-chat");
    }
    requireString(config.channel.conversationId, "channel.conversationId");
    requireString(config.channel.peerUserId, "channel.peerUserId");
    requireString(config.channel.peerOpenDingTalkId, "channel.peerOpenDingTalkId");
    requireString(config.channel.selfUserId, "channel.selfUserId");
    requireString(config.channel.selfOpenDingTalkId, "channel.selfOpenDingTalkId");
    const sameUserId = config.channel.peerUserId === config.channel.selfUserId;
    const sameOpenId = config.channel.peerOpenDingTalkId === config.channel.selfOpenDingTalkId;
    if (sameUserId !== sameOpenId) {
      throw new ControllerError("CONFIG_CHANNEL_IDENTITY_COLLISION", "Peer and self identity must match on both ID fields or neither");
    }
    if (sameUserId && config.channel.kind !== "self-chat") {
      throw new ControllerError("CONFIG_SELF_CHAT_REQUIRES_OPT_IN", "Matching peer and self identities require channel.kind=self-chat");
    }
    if (!sameUserId && config.channel.kind === "self-chat") {
      throw new ControllerError("CONFIG_SELF_CHAT_IDENTITY_MISMATCH", "Self-chat commands require peer and self dual IDs to match");
    }

    const taskEnrolled = config.task?.enrolled !== false && config.task !== undefined;
    if (config.mode === "active" && !taskEnrolled) {
      throw new ControllerError("CONFIG_TASK_REQUIRED", "Active mode requires an enrolled dedicated Codex task");
    }
    if (taskEnrolled) {
      requireString(config.task.threadId, "task.threadId");
      requireString(config.task.expectedTitle, "task.expectedTitle");
      requireString(config.task.cwd, "task.cwd");
      requireString(config.task.permissionProfile, "task.permissionProfile");
    } else {
      if (config.delivery.mode !== "disabled") {
        throw new ControllerError("CONFIG_TASKLESS_DELIVERY", "Observe mode without a task requires disabled delivery");
      }
      if (Object.values(config.actions ?? {}).some((action) => action.enabled === true)) {
        throw new ControllerError("CONFIG_TASKLESS_ACTION", "Observe mode without a task requires every action to be disabled");
      }
    }
    if (config.mode === "active") {
      if (config.channel.kind !== "self-chat") {
        throw new ControllerError("CONFIG_ACTIVE_CHANNEL", "Active mode is limited to the enrolled self-chat");
      }
      if (config.delivery.mode !== "trusted-self" || config.delivery.trustedRecipientName !== TRUSTED_RECIPIENT_NAME) {
        throw new ControllerError("CONFIG_ACTIVE_DELIVERY", "Active mode requires trusted-self delivery to 欧阳斌");
      }
      if (!matchesTrustedRecipient(config.channel.peerUserId, config.channel.peerOpenDingTalkId) ||
          !matchesTrustedRecipient(config.channel.selfUserId, config.channel.selfOpenDingTalkId)) {
        throw new ControllerError("CONFIG_ACTIVE_IDENTITY_PIN", "Active mode requires the fixed trusted recipient identity");
      }
      if (config.task.permissionProfile !== ":read-only") {
        throw new ControllerError("CONFIG_ACTIVE_PERMISSION", "Active mode requires the :read-only permission profile");
      }
      const enabledActions = Object.entries(config.actions ?? {})
        .filter(([, action]) => action.enabled === true)
        .map(([alias]) => alias);
      if (enabledActions.length !== 1 || enabledActions[0] !== "health-check") {
        throw new ControllerError("CONFIG_ACTIVE_ACTIONS", "Active mode enables only the fixed health-check action");
      }
      const healthAction = config.actions["health-check"];
      const requiredPromptPath = path.join(normalized.projectRoot, "config", "actions", "health-check.txt");
      const configuredPromptPath = resolveLocal(normalized.projectRoot, healthAction.promptFile);
      if (path.resolve(configuredPromptPath) !== path.resolve(requiredPromptPath) ||
          healthAction.promptSha256 !== HEALTH_CHECK_PROMPT_SHA256) {
        throw new ControllerError("CONFIG_ACTIVE_ACTION_PIN", "Active health-check must use the built-in prompt path and pinned hash");
      }
    }
  }

  normalized.actions = normalized.actions ?? {};
  for (const [alias, action] of Object.entries(normalized.actions)) {
    if (!/^[a-z0-9][a-z0-9-]{0,62}$/u.test(alias)) {
      throw new ControllerError("CONFIG_ACTION_ALIAS", `Invalid action alias: ${alias}`);
    }
    const promptPath = resolveLocal(normalized.projectRoot, action.promptFile);
    normalized.actions[alias].promptPath = promptPath;
    if (options.verifyActions !== false && !PLACEHOLDER.test(action.promptSha256)) {
      await access(promptPath, constants.R_OK);
      const prompt = await readFile(promptPath);
      if (sha256(prompt) !== action.promptSha256) {
        throw new ControllerError("CONFIG_ACTION_HASH", `Action hash mismatch: ${alias}`);
      }
    }
  }

  return normalized;
}

export function evaluateGates(config) {
  const required = [
    "dwsProtocolVerified",
    "codexPermissionVerified",
    "codexReconciliationVerified",
    "outboundAuthorizationVerified"
  ];
  const missing = required.filter((name) => config.gates?.[name] !== true);
  const activeRequested = config.mode === "active";
  const deliveryAllowed = new Set(["trusted-service-account", "trusted-self", "local-approval"]).has(config.delivery?.mode);
  const taskEnrolled = config.task?.enrolled !== false && Boolean(config.task?.threadId);
  const permissionProfileSafe = taskEnrolled && config.task?.permissionProfile === ":read-only";
  const trustedIdentityPinned = matchesTrustedRecipient(
    config.channel?.peerUserId, config.channel?.peerOpenDingTalkId
  ) && matchesTrustedRecipient(config.channel?.selfUserId, config.channel?.selfOpenDingTalkId);
  return {
    activeRequested,
    missing,
    deliveryAllowed,
    taskEnrolled,
    permissionProfileSafe,
    trustedIdentityPinned,
    runEnabled: activeRequested && missing.length === 0 && deliveryAllowed && permissionProfileSafe &&
      config.channel?.kind === "self-chat" && config.delivery?.mode === "trusted-self" &&
      config.delivery?.trustedRecipientName === TRUSTED_RECIPIENT_NAME && trustedIdentityPinned,
    observeOnly: !activeRequested || missing.length > 0 || !deliveryAllowed || !permissionProfileSafe
  };
}
