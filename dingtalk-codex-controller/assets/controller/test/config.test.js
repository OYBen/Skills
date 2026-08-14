import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { HEALTH_CHECK_PROMPT_SHA256, loadConfig } from "../src/config.js";
import { trustedOpenDingTalkId, trustedUserId } from "../test-support/trusted-fixture.js";

const healthPrompt = "Inspect only the dedicated controller workspace and report whether it is healthy in no more than 300 Unicode characters. Do not access credentials, DingTalk, email, browser, network resources, files outside the workspace, or destructive tools. Do not modify files.\n";

function tasklessSelfConfig(overrides = {}) {
  return {
    schemaVersion: 1,
    mode: "observe",
    channel: {
      kind: "self-chat",
      conversationId: "conv",
      peerUserId: "self-user",
      peerOpenDingTalkId: "self-open",
      selfUserId: "self-user",
      selfOpenDingTalkId: "self-open"
    },
    task: { enrolled: false },
    actions: {},
    gates: {
      dwsProtocolVerified: false,
      codexPermissionVerified: false,
      codexReconciliationVerified: false,
      outboundAuthorizationVerified: false
    },
    delivery: { mode: "disabled" },
    paths: { database: "data/controller.db", payloads: "data/payloads" },
    ...overrides
  };
}

function activeSelfConfig() {
  const config = {
    ...tasklessSelfConfig(),
    mode: "active",
    task: {
      enrolled: true,
      threadId: "thread",
      expectedTitle: "DingTalk Controller Read-Only",
      cwd: "sandbox",
      permissionProfile: ":read-only"
    },
    actions: {
      "health-check": {
        enabled: true,
        promptFile: "config/actions/health-check.txt",
        promptSha256: HEALTH_CHECK_PROMPT_SHA256
      }
    },
    gates: {
      dwsProtocolVerified: true,
      codexPermissionVerified: true,
      codexReconciliationVerified: true,
      outboundAuthorizationVerified: true
    },
    delivery: { mode: "trusted-self", trustedRecipientName: "欧阳斌" }
  };
  config.channel.peerUserId = trustedUserId;
  config.channel.selfUserId = trustedUserId;
  config.channel.peerOpenDingTalkId = trustedOpenDingTalkId;
  config.channel.selfOpenDingTalkId = trustedOpenDingTalkId;
  return config;
}

async function withConfig(config, callback) {
  const directory = await mkdtemp(path.join(tmpdir(), "controller-config-"));
  const configDirectory = path.join(directory, "config");
  const configPath = path.join(configDirectory, "config.json");
  try {
    await mkdir(path.join(configDirectory, "actions"), { recursive: true });
    await writeFile(path.join(configDirectory, "actions", "health-check.txt"), healthPrompt, "utf8");
    await writeFile(configPath, JSON.stringify(config), "utf8");
    return await callback(configPath);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test("loads explicit taskless self-chat observe configuration", async () => {
  await withConfig(tasklessSelfConfig(), async (configPath) => {
    const config = await loadConfig(configPath);
    assert.equal(config.channel.kind, "self-chat");
    assert.equal(config.task.enrolled, false);
  });
});

test("self-chat requires both enrolled identity fields to match", async () => {
  const config = tasklessSelfConfig();
  config.channel.peerOpenDingTalkId = "other-open";
  await withConfig(config, async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_CHANNEL_IDENTITY_COLLISION" });
  });
});

test("taskless observe forbids active mode, delivery, and enabled actions", async () => {
  await withConfig(tasklessSelfConfig({ mode: "active" }), async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_TASK_REQUIRED" });
  });
  await withConfig(tasklessSelfConfig({ delivery: { mode: "local-approval" } }), async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_TASKLESS_DELIVERY" });
  });
  const enabled = tasklessSelfConfig();
  enabled.actions = { health: { enabled: true, promptFile: "missing", promptSha256: "<unverified>" } };
  await withConfig(enabled, async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_TASKLESS_ACTION" });
  });
});

test("active mode is restricted to the trusted self-chat health check", async () => {
  await withConfig(activeSelfConfig(), async (configPath) => {
    const config = await loadConfig(configPath);
    assert.equal(config.mode, "active");
  });
  const wrongRecipient = activeSelfConfig();
  wrongRecipient.delivery.trustedRecipientName = "Other";
  await withConfig(wrongRecipient, async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_ACTIVE_DELIVERY" });
  });
  const arbitraryAction = activeSelfConfig();
  arbitraryAction.actions = { arbitrary: arbitraryAction.actions["health-check"] };
  await withConfig(arbitraryAction, async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_ACTIVE_ACTIONS" });
  });
  const changedHash = activeSelfConfig();
  changedHash.actions["health-check"].promptSha256 = "0".repeat(64);
  await withConfig(changedHash, async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_ACTIVE_ACTION_PIN" });
  });
  const changedIdentity = activeSelfConfig();
  changedIdentity.channel.peerUserId = "other";
  changedIdentity.channel.selfUserId = "other";
  await withConfig(changedIdentity, async (configPath) => {
    await assert.rejects(loadConfig(configPath), { code: "CONFIG_ACTIVE_IDENTITY_PIN" });
  });
});
