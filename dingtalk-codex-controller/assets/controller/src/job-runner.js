import path from "node:path";
import { isoNow, readUtf8, sha256, writeFileAtomic } from "./util.js";
import { ControllerError } from "./errors.js";
import { evaluateGates } from "./config.js";
import { inspectRolloutTurn, listAllThreads, threadStatusType } from "./thread-directory.js";
import { instructionForJob, resolveThreadSelector } from "./thread-routing.js";

function profileItems(response) {
  const items = response?.profiles ?? response?.items ?? response?.data ?? [];
  return Array.isArray(items) ? items : [];
}

function threadFrom(response) {
  return response?.thread ?? response;
}

function permissionProfileFrom(response) {
  return response?.activePermissionProfile?.id
    ?? response?.thread?.activePermissionProfile?.id
    ?? response?.permissionProfile?.id
    ?? null;
}

function sandboxTypeFrom(response) {
  return response?.sandbox?.type ?? response?.thread?.sandbox?.type ?? null;
}

function fenced(context, callback) {
  return context.leaseTransaction ? context.leaseTransaction(callback) : callback();
}

function assertLease(context) {
  context.assertLease?.();
}

export function assertThreadIdentityAndAvailability(response, config, options = {}) {
  const thread = threadFrom(response);
  if (!thread || thread.id !== config.task.threadId) {
    throw new ControllerError("THREAD_ID_MISMATCH", "Codex returned a different thread");
  }
  const title = thread.name ?? thread.title ?? null;
  if (title !== config.task.expectedTitle) {
    throw new ControllerError("THREAD_TITLE_MISMATCH", "Codex task title does not match enrollment");
  }
  const status = typeof thread.status === "string" ? thread.status : thread.status?.type;
  if (!new Set(["notLoaded", "idle"]).has(status)) {
    throw new ControllerError("THREAD_NOT_IDLE", "Codex task is active or unavailable");
  }
  const activeProfile = permissionProfileFrom(response);
  if (options.requireProfile === true) {
    const legacyReadOnly = config.task.permissionProfile === ":read-only" && sandboxTypeFrom(response) === "readOnly";
    if (activeProfile !== config.task.permissionProfile && !legacyReadOnly) {
      throw new ControllerError("THREAD_PERMISSION_MISMATCH", "Codex task did not report the enrolled read-only boundary");
    }
    if (!response?.cwd || path.resolve(response.cwd) !== path.resolve(config.task.cwd)) {
      throw new ControllerError("THREAD_CWD_MISMATCH", "Codex task resolved a different working directory");
    }
  }
  return thread;
}

function quarantineUnknown(context, requestId, errorCode) {
  const { store } = context;
  let changed = false;
  try {
    changed = fenced(context, () => store.transitionJob(requestId, "START_CALL_IN_FLIGHT", "START_UNKNOWN", { error_code: errorCode }));
  } catch (error) {
    if (error?.code === "CONTROLLER_LEASE_LOST") throw error;
    throw new ControllerError("START_STATE_PERSIST_FAILED", "Could not persist ambiguous Codex start state", { cause: error.code });
  }
  if (!changed) {
    throw new ControllerError("START_STATE_PERSIST_FAILED", "Could not persist ambiguous Codex start state");
  }
  return { status: "START_UNKNOWN", errorCode };
}

export async function startFixedAction(context) {
  const { config, store, codexClient, requestId } = context;
  const gates = evaluateGates(config);
  if (!gates.runEnabled || context.gates?.runEnabled !== true) {
    throw new ControllerError("RUN_GATE_BLOCKED", "Run is disabled until every implementation gate passes");
  }
  const job = store.getJob(requestId);
  if (!job) throw new ControllerError("JOB_NOT_FOUND", "Job was not found");
  if (job.state !== "ACK_SENT") {
    throw new ControllerError("JOB_STATE", `Job cannot start from ${job.state}`);
  }
  if (job.command !== "run" || !job.action_alias) {
    throw new ControllerError("JOB_ACTION_REQUIRED", "Only a catalog-backed run job may start Codex");
  }
  const action = config.actions?.[job.action_alias];
  if (!action || action.enabled !== true || !action.promptPath || !action.promptSha256) {
    throw new ControllerError("ACTION_DISABLED", "Action is missing, disabled, or incomplete");
  }
  const promptText = await readUtf8(action.promptPath);
  if (sha256(promptText) !== action.promptSha256 || job.prompt_sha256 !== action.promptSha256) {
    throw new ControllerError("ACTION_HASH_MISMATCH", "Action text does not match its pinned hash");
  }

  assertLease(context);
  const profiles = await codexClient.listPermissionProfiles(config.task.cwd);
  assertLease(context);
  const profile = profileItems(profiles).find((item) => (item.id ?? item.name) === config.task.permissionProfile);
  if (!profile || (profile.allowed ?? profile.isAllowed) !== true) {
    throw new ControllerError("PERMISSION_PROFILE_UNAVAILABLE", "Enrolled Codex permission profile is not allowed");
  }
  assertLease(context);
  const read = await codexClient.readThread(config.task.threadId, false);
  assertLease(context);
  assertThreadIdentityAndAvailability(read, config);
  assertLease(context);
  const resumed = await codexClient.resumeThread(config.task.threadId, {
    cwd: config.task.cwd,
    permissionProfile: config.task.permissionProfile,
    approvalPolicy: "never"
  });
  assertLease(context);
  assertThreadIdentityAndAvailability(resumed, config, { requireProfile: true });

  const now = isoNow(context.clock);
  if (!fenced(context, () => store.transitionJob(requestId, "ACK_SENT", "START_INTENT_RECORDED", { start_attempted_at: now }))) {
    throw new ControllerError("JOB_RACE", "Job state changed before start intent was recorded");
  }
  if (!fenced(context, () => store.transitionJob(requestId, "START_INTENT_RECORDED", "START_CALL_IN_FLIGHT"))) {
    throw new ControllerError("JOB_RACE", "Job state changed before start call");
  }

  try {
    assertLease(context);
    const response = await codexClient.startTurn(config.task.threadId, promptText, {
      cwd: config.task.cwd,
      approvalPolicy: "never",
      permissionProfile: config.task.permissionProfile
    });
    assertLease(context);
    const turnId = response?.turn?.id ?? response?.id;
    if (!turnId) {
      return quarantineUnknown(context, requestId, "TURN_ID_MISSING");
    }
    let persisted = false;
    try {
      persisted = fenced(context, () => store.transitionJob(requestId, "START_CALL_IN_FLIGHT", "RUNNING", { codex_turn_id: turnId }));
    } catch (error) {
      if (error?.code === "CONTROLLER_LEASE_LOST") throw error;
      return quarantineUnknown(context, requestId, error.code ?? "TURN_STATE_PERSIST_FAILED");
    }
    if (!persisted) return quarantineUnknown(context, requestId, "TURN_STATE_PERSIST_FAILED");
    return { status: "RUNNING", turnId };
  } catch (error) {
    if (error instanceof ControllerError && error.code === "START_STATE_PERSIST_FAILED") throw error;
    if (error?.code === "CONTROLLER_LEASE_LOST") throw error;
    return quarantineUnknown(context, requestId, error.code ?? "TURN_START_AMBIGUOUS");
  }
}

export async function startTargetInstruction(context) {
  const { config, store, desktopClient, requestId } = context;
  const gates = evaluateGates(config);
  if (!gates.runEnabled || context.gates?.runEnabled !== true) {
    throw new ControllerError("RUN_GATE_BLOCKED", "Task instruction is disabled until every implementation gate passes");
  }
  const job = store.getJob(requestId);
  if (!job || job.state !== "ACK_SENT") throw new ControllerError("JOB_STATE", "Instruction job is not ready to start");
  if (job.command !== "send" || !job.target_thread_id || !job.instruction_path || !job.instruction_sha256) {
    throw new ControllerError("JOB_INSTRUCTION_REQUIRED", "Instruction job is incomplete");
  }
  const storedInstruction = await readUtf8(job.instruction_path);
  if (sha256(storedInstruction) !== job.instruction_sha256) {
    throw new ControllerError("INSTRUCTION_HASH_MISMATCH", "Persisted instruction failed integrity verification");
  }
  const instruction = instructionForJob(storedInstruction, job.watch_thread_id);

  const preflight = await preflightTargetInstruction(context);
  if (preflight.status === "QUEUED") {
    throw new ControllerError(preflight.reason, "Codex target task is not ready for immediate execution");
  }
  const { target, ownerClientId } = preflight;

  const now = isoNow(context.clock);
  if (!fenced(context, () => store.transitionJob(requestId, "ACK_SENT", "START_INTENT_RECORDED", { start_attempted_at: now }))) {
    throw new ControllerError("JOB_RACE", "Job state changed before instruction start intent was recorded");
  }
  if (!fenced(context, () => store.transitionJob(requestId, "START_INTENT_RECORDED", "START_CALL_IN_FLIGHT"))) {
    throw new ControllerError("JOB_RACE", "Job state changed before instruction start call");
  }

  try {
    assertLease(context);
    const response = await desktopClient.startThreadTurn(target.id, instruction, { ownerClientId });
    assertLease(context);
    const turnId = response?.turn?.id ?? response?.id;
    if (!turnId) return quarantineUnknown(context, requestId, "TURN_ID_MISSING");
    const persisted = fenced(context, () => store.transitionJob(requestId, "START_CALL_IN_FLIGHT", "RUNNING", { codex_turn_id: turnId }));
    if (!persisted) return quarantineUnknown(context, requestId, "TURN_STATE_PERSIST_FAILED");
    return { status: "RUNNING", turnId };
  } catch (error) {
    if (error?.code === "CONTROLLER_LEASE_LOST" || error?.code === "START_STATE_PERSIST_FAILED") throw error;
    return quarantineUnknown(context, requestId, error.code ?? "TURN_START_AMBIGUOUS");
  }
}

export async function preflightTargetInstruction(context) {
  const { config, store, desktopClient, requestId } = context;
  const job = store.getJob(requestId);
  if (!job || !new Set(["PENDING", "QUEUED", "ACK_SENT"]).has(job.state)) {
    throw new ControllerError("JOB_STATE", "Instruction job is not ready for preflight");
  }
  assertLease(context);
  const directory = await listAllThreads(context.threadDirectory);
  assertLease(context);
  const selector = job.target_thread_id ?? job.target_selector;
  const target = resolveThreadSelector(selector, directory, {
    store,
    conversationId: config.channel.conversationId
  });
  if (target.archived) {
    throw new ControllerError("THREAD_ARCHIVED", "Archived Codex tasks cannot receive instructions");
  }
  const status = threadStatusType(target);
  if (status === "active") {
    return { status: "QUEUED", reason: "THREAD_ACTIVE", target };
  }
  if (status !== "idle") {
    throw new ControllerError("THREAD_STATUS_UNKNOWN", "Codex target task idle state cannot be verified");
  }
  if (!desktopClient) {
    throw new ControllerError("DESKTOP_IPC_UNAVAILABLE", "Codex Desktop IPC client is unavailable");
  }
  const ownerClientId = await desktopClient.findThreadOwner(target.id);
  assertLease(context);
  if (!ownerClientId) {
    return { status: "QUEUED", reason: "DESKTOP_THREAD_OWNER_UNAVAILABLE", target };
  }
  return { status: "READY", target, ownerClientId };
}

export async function completeJob(context) {
  const { store, requestId, resultText, resultPath } = context;
  const job = store.getJob(requestId);
  if (!job || job.state !== "RUNNING") {
    throw new ControllerError("JOB_STATE", "Only a running job can complete");
  }
  assertLease(context);
  await writeFileAtomic(resultPath, resultText);
  assertLease(context);
  const digest = sha256(resultText);
  const completedAt = isoNow(context.clock);
  if (!fenced(context, () => store.transitionJob(requestId, "RUNNING", "COMPLETED", {
    result_path: resultPath,
    result_sha256: digest,
    completed_at: completedAt,
    observation_time: completedAt
  }))) {
    throw new ControllerError("JOB_RACE", "Job state changed before completion");
  }
  return { status: "COMPLETED", resultPath, resultSha256: digest };
}

export async function completeLocalJob(context) {
  const { store, requestId, resultText, resultPath } = context;
  const job = store.getJob(requestId);
  if (!job || job.state !== "PENDING") {
    throw new ControllerError("JOB_STATE", "Only a pending local job can complete");
  }
  assertLease(context);
  await writeFileAtomic(resultPath, resultText);
  assertLease(context);
  const digest = sha256(resultText);
  const completedAt = isoNow(context.clock);
  if (!fenced(context, () => store.transitionJob(requestId, "PENDING", "COMPLETED", {
    result_path: resultPath,
    result_sha256: digest,
    completed_at: completedAt,
    observation_time: completedAt
  }))) {
    throw new ControllerError("JOB_RACE", "Job state changed before local completion");
  }
  return { status: "COMPLETED", resultPath, resultSha256: digest };
}

export async function reconcileRunningJob(context) {
  const { config, store, requestId, resultPath } = context;
  const job = store.getJob(requestId);
  if (!job || job.state !== "RUNNING" || !job.codex_turn_id) {
    throw new ControllerError("JOB_STATE", "Only a running job with a turn ID can be reconciled");
  }
  assertLease(context);
  const targetThreadId = job.target_thread_id ?? config.task.threadId;
  const directory = await listAllThreads(context.threadDirectory);
  assertLease(context);
  const target = directory.find((thread) => thread.id === targetThreadId);
  if (!target) throw new ControllerError("THREAD_NOT_FOUND", "Codex target task disappeared during reconciliation");
  const turn = await inspectRolloutTurn(target.rolloutPath, job.codex_turn_id);
  assertLease(context);
  if (turn.status === "MISSING") return { status: "RUNNING", reason: turn.errorCode };
  if (turn.status === "RUNNING") return { status: "RUNNING" };
  if (turn.status === "FAILED") {
    const errorCode = turn.errorCode ?? "TURN_FAILED";
    if (!fenced(context, () => store.transitionJob(requestId, "RUNNING", "FAILED", {
      completed_at: isoNow(context.clock), error_code: errorCode
    }))) throw new ControllerError("JOB_RACE", "Job state changed before failure was persisted");
    return { status: "FAILED", errorCode };
  }
  return completeJob({ ...context, resultText: turn.resultText, resultPath });
}
