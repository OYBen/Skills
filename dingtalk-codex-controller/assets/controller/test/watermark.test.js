import test from "node:test";
import assert from "node:assert/strict";
import { prepareGeneratedText } from "../src/watermark.js";

test("uses the installed scripts and counts the watermarked final text", async () => {
  const prepared = await prepareGeneratedText("Controller status: observe-only");
  assert.ok(prepared.text.startsWith("【AI生成】\n"));
  assert.equal(prepared.metrics.withinLimit, true);
  assert.equal(prepared.metrics.characterCount, Array.from(prepared.text).length);
});
