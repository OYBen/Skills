import test from "node:test";
import assert from "node:assert/strict";
import { Store } from "../src/store.js";
import {
  availabilityLabel,
  instructionForJob,
  resolveThreadSelector
} from "../src/thread-routing.js";

const threads = [
  { id: "00000000-0000-0000-0000-000000000001", name: "示例任务-执行", archived: false, status: { type: "idle" } },
  { id: "00000000-0000-0000-0000-000000000002", name: "示例任务-监控", archived: false, status: { type: "active" } },
  { id: "00000000-0000-0000-0000-000000000003", name: "示例任务-执行-A", archived: false, status: { type: "idle" } }
];

test("resolves task IDs, stable short numbers, exact names and unique partial names", () => {
  const store = new Store(":memory:");
  try {
    store.saveThreadSelections("conv", [{ number: 7, threadId: threads[0].id }]);
    const options = { store, conversationId: "conv" };
    assert.equal(resolveThreadSelector(threads[0].id, threads, options).id, threads[0].id);
    assert.equal(resolveThreadSelector("7", threads, options).id, threads[0].id);
    assert.equal(resolveThreadSelector("示例任务-监控", threads, options).id, threads[1].id);
    assert.equal(resolveThreadSelector("执行-A", threads, options).id, threads[2].id);
    assert.throws(() => resolveThreadSelector("示例任务", threads, options), { code: "THREAD_SELECTOR_AMBIGUOUS" });
    assert.throws(() => resolveThreadSelector("99", threads, options), { code: "THREAD_SELECTION_EXPIRED" });
  } finally {
    store.close();
  }
});

test("persists target/watch bindings without storing raw conversation IDs", () => {
  const store = new Store(":memory:");
  try {
    store.setBinding("private-conversation", { targetThreadId: threads[0].id });
    store.setBinding("private-conversation", { watchThreadId: threads[1].id });
    const binding = store.getBinding("private-conversation");
    assert.equal(binding.target_thread_id, threads[0].id);
    assert.equal(binding.watch_thread_id, threads[1].id);
    assert.match(binding.updated_at, /^\d{4}-\d{2}-\d{2}T/u);
    const serialized = JSON.stringify(store.db.prepare("SELECT * FROM controller_bindings").all());
    assert.doesNotMatch(serialized, /private-conversation/u);
  } finally {
    store.close();
  }
});

test("labels actionable availability and wraps watch context deterministically", () => {
  assert.equal(availabilityLabel(threads[0], true), "空闲，可立即发送");
  assert.equal(availabilityLabel(threads[0], false), "未加载，需在 Codex Desktop 打开");
  assert.equal(availabilityLabel(threads[1], null), "执行中，可排队");
  assert.equal(instructionForJob("查询状态", threads[1].id), [
    "针对以下监控对象处理用户指令。",
    `监控对象 Codex 任务 ID：${threads[1].id}`,
    "用户指令：查询状态"
  ].join("\n"));
});
