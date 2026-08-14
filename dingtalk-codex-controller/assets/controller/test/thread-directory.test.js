import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import path from "node:path";
import { tmpdir } from "node:os";
import { formatThreadPage, inspectRolloutTurn, listAllThreads } from "../src/thread-directory.js";

function event(type, turnId, values = {}) {
  return JSON.stringify({
    timestamp: values.timestamp ?? "2026-08-13T05:00:00.000Z",
    type: "event_msg",
    payload: { type, turn_id: turnId, ...values.payload }
  });
}

test("reads the Codex Desktop task catalog without App Server pagination", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "desktop-thread-catalog-"));
  const databasePath = path.join(directory, "state.sqlite");
  const idleRollout = path.join(directory, "idle.jsonl");
  const activeRollout = path.join(directory, "active.jsonl");
  await writeFile(idleRollout, `${event("task_started", "turn-idle")}\n${event("task_complete", "turn-idle")}\n`, "utf8");
  await writeFile(activeRollout, `${event("task_started", "turn-active", { timestamp: new Date().toISOString() })}\n`, "utf8");
  const database = new DatabaseSync(databasePath);
  database.exec(`CREATE TABLE threads(
    id TEXT PRIMARY KEY, rollout_path TEXT, cwd TEXT, title TEXT, name TEXT,
    archived INTEGER, updated_at INTEGER, updated_at_ms INTEGER
  )`);
  database.prepare("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)")
    .run("b", idleRollout, "D:\\idle", "Idle title", null, 0, 2, 2000);
  database.prepare("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)")
    .run("a", activeRollout, "D:\\active", "Active title", "Active name", 0, 3, 3000);
  database.prepare("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)")
    .run("c", idleRollout, "D:\\archived", "Archived", null, 1, 1, 1000);
  database.close();
  try {
    const threads = await listAllThreads(databasePath);
    assert.deepEqual(threads.map((item) => [item.id, item.archived, item.status.type]), [
      ["a", false, "active"], ["b", false, "idle"], ["c", true, "archived"]
    ]);
    assert.equal(threads[1].rolloutPath, idleRollout);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("reconciles only the exact rollout turn result", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "desktop-rollout-result-"));
  const rollout = path.join(directory, "rollout.jsonl");
  await writeFile(rollout, [
    event("task_started", "turn-target"),
    event("task_complete", "turn-other", { payload: { last_agent_message: "wrong" } }),
    event("task_complete", "turn-target", { payload: { last_agent_message: "Exact result." } })
  ].join("\n"), "utf8");
  try {
    assert.deepEqual(await inspectRolloutTurn(rollout, "turn-target"), {
      status: "COMPLETED", resultText: "Exact result.", completedAt: "2026-08-13T05:00:00.000Z"
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("marks a started turn interrupted when a later turn supersedes it", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "desktop-rollout-interrupted-"));
  const rollout = path.join(directory, "rollout.jsonl");
  await writeFile(rollout, `${event("task_started", "turn-target")}\n${event("task_started", "turn-next")}\n`, "utf8");
  try {
    assert.deepEqual(await inspectRolloutTurn(rollout, "turn-target"), {
      status: "FAILED", errorCode: "TURN_INTERRUPTED"
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("formats three complete IDs per DingTalk page", () => {
  const threads = Array.from({ length: 4 }, (_, index) => ({
    id: `00000000-0000-0000-0000-00000000000${index}`,
    name: `Task ${index}`,
    status: { type: index === 0 ? "active" : "idle" },
    archived: false
  }));
  const first = formatThreadPage(threads, 1);
  assert.match(first, /1\/2 页/u);
  assert.match(first, /00000000-0000-0000-0000-000000000002/u);
  assert.doesNotMatch(first, /00000000-0000-0000-0000-000000000003/u);
  assert.match(formatThreadPage(threads, 3), /页码超出范围/u);
});

test("does not expose task previews when a task has no name", () => {
  const text = formatThreadPage([{
    id: "00000000-0000-0000-0000-000000000000",
    name: null,
    preview: "private instruction preview",
    status: { type: "idle" },
    archived: false
  }], 1);
  assert.match(text, /未命名任务/u);
  assert.doesNotMatch(text, /private instruction preview/u);
});
