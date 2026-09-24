import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../lib/autosave-queue.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { createAutosaveQueue } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("rapid changes serialize requests and save only the latest pending card", async () => {
  const requests = [];
  const queue = createAutosaveQueue(value => {
    const request = { value, ...deferred() };
    requests.push(request);
    return request.promise;
  });
  queue.submit({ a: 1 });
  queue.submit({ a: 2 });
  queue.submit({ a: 2, b: 3 });
  assert.equal(requests.length, 1);
  assert.equal(queue.getSnapshot().status, "saving");
  requests[0].resolve();
  await tick();
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[1].value, { a: 2, b: 3 });
  assert.equal(queue.hasUnsavedChanges(), true);
  requests[1].resolve();
  await tick();
  assert.equal(queue.getSnapshot().status, "saved");
  assert.equal(queue.hasUnsavedChanges(), false);
});

test("failed writes retain the newest card and retry cannot overlap a write", async () => {
  const first = deferred();
  const calls = [];
  const queue = createAutosaveQueue(value => { calls.push(value); return calls.length === 1 ? first.promise : Promise.resolve(); });
  queue.submit(1);
  queue.submit(2);
  await queue.retry();
  assert.deepEqual(calls, [1]);
  first.reject(new Error("Offline"));
  await tick();
  assert.equal(queue.getSnapshot().status, "error");
  assert.equal(queue.hasUnsavedChanges(), true);
  await queue.retry();
  assert.deepEqual(calls, [1, 2]);
  assert.equal(queue.getSnapshot().status, "saved");
  assert.equal(queue.hasUnsavedChanges(), false);
});

test("deadline rejection stays unsaved and does not retry automatically", async () => {
  let calls = 0;
  const queue = createAutosaveQueue(async () => { calls++; throw new Error("Picks are locked"); });
  queue.submit({ a: 1 });
  await tick();
  assert.equal(calls, 1);
  assert.equal(queue.getSnapshot().error.message, "Picks are locked");
  assert.equal(queue.hasUnsavedChanges(), true);
});

test("a new selection after failure saves the new card", async () => {
  const calls = [];
  const queue = createAutosaveQueue(async value => { calls.push(value); if (calls.length === 1) throw new Error("Offline"); });
  queue.submit(1);
  await tick();
  queue.submit(2);
  await tick();
  assert.deepEqual(calls, [1, 2]);
  assert.equal(queue.getSnapshot().status, "saved");
});
