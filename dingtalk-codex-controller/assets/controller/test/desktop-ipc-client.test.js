import test from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import { randomUUID } from "node:crypto";
import { DesktopIpcClient, extractDesktopTurnId } from "../src/codex-client.js";

function frame(message) {
  const body = Buffer.from(JSON.stringify(message), "utf8");
  const result = Buffer.alloc(4 + body.length);
  result.writeUInt32LE(body.length, 0);
  body.copy(result, 4);
  return result;
}

function attachReader(socket, callback) {
  let buffer = Buffer.alloc(0);
  socket.on("data", (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);
    while (buffer.length >= 4) {
      const length = buffer.readUInt32LE(0);
      if (buffer.length < length + 4) return;
      callback(JSON.parse(buffer.subarray(4, length + 4).toString("utf8")));
      buffer = buffer.subarray(length + 4);
    }
  });
}

test("routes a turn to the discovered Codex Desktop owner", async () => {
  const pipePath = `\\\\.\\pipe\\dingtalk-controller-test-${process.pid}-${randomUUID()}`;
  const requests = [];
  const server = net.createServer((socket) => attachReader(socket, (request) => {
    requests.push(request);
    if (request.method === "initialize") {
      socket.write(frame({
        type: "response", requestId: request.requestId, resultType: "success",
        method: "initialize", handledByClientId: "controller-client",
        result: { clientId: "controller-client" }
      }));
    } else if (request.method === "thread-owner-discovery") {
      socket.write(frame({
        type: "response", requestId: request.requestId, resultType: "success",
        method: request.method, handledByClientId: "desktop-owner", result: {}
      }));
    } else if (request.method === "thread-follower-start-turn") {
      socket.write(frame({
        type: "response", requestId: request.requestId, resultType: "success",
        method: request.method, handledByClientId: "desktop-owner",
        result: { result: { turn: { id: "desktop-turn" } } }
      }));
    }
  }));
  await new Promise((resolve, reject) => server.listen(pipePath, resolve).once("error", reject));
  const client = new DesktopIpcClient({ pipePath, timeoutMs: 2_000 });
  try {
    const owner = await client.findThreadOwner("thread-1");
    const started = await client.startThreadTurn("thread-1", "Do work", { ownerClientId: owner });
    assert.equal(owner, "desktop-owner");
    assert.equal(started.turn.id, "desktop-turn");
    const start = requests.find((request) => request.method === "thread-follower-start-turn");
    assert.equal(start.version, 1);
    assert.equal(start.targetClientId, "desktop-owner");
    assert.equal(start.params.conversationId, "thread-1");
    assert.deepEqual(start.params.turnStartParams.input, [{ type: "text", text: "Do work", text_elements: [] }]);
    assert.match(start.params.turnStartParams.clientUserMessageId, /^[0-9a-f-]{36}$/u);
  } finally {
    await client.stop();
    await new Promise((resolve) => server.close(resolve));
  }
});

test("maps no-client-found to an unavailable Desktop owner", async () => {
  const pipePath = `\\\\.\\pipe\\dingtalk-controller-test-${process.pid}-${randomUUID()}`;
  const server = net.createServer((socket) => attachReader(socket, (request) => {
    if (request.method === "initialize") {
      socket.write(frame({ type: "response", requestId: request.requestId, resultType: "success", method: "initialize", result: { clientId: "client" } }));
    } else {
      socket.write(frame({ type: "response", requestId: request.requestId, resultType: "error", error: "no-client-found" }));
    }
  }));
  await new Promise((resolve, reject) => server.listen(pipePath, resolve).once("error", reject));
  const client = new DesktopIpcClient({ pipePath, timeoutMs: 2_000 });
  try {
    assert.equal(await client.findThreadOwner("missing-thread"), null);
  } finally {
    await client.stop();
    await new Promise((resolve) => server.close(resolve));
  }
});

test("extracts only a concrete turn ID from nested Desktop responses", () => {
  assert.equal(extractDesktopTurnId({ result: { result: { turn: { id: "turn-1" } } } }), "turn-1");
  assert.equal(extractDesktopTurnId({ result: { ok: true } }), null);
});
