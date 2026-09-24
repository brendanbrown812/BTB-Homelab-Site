import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../lib/draft-autosave.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { createDraftAutosave } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function session(save, delay = 2000) {
  let backup = null;
  return { controller: createDraftAutosave({ initial: "original", save, delay, remember: value => { backup = value; }, forget: () => { backup = null; } }), backup: () => backup };
}

test("typing saves a recovery copy immediately and debounces the server write", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const writes = [];
  const { controller, backup } = session(async value => { writes.push(value); });
  controller.edit("first");
  assert.equal(backup(), "first");
  t.mock.timers.tick(1500);
  controller.edit("latest");
  t.mock.timers.tick(1500);
  assert.deepEqual(writes, []);
  t.mock.timers.tick(500);
  await tick();
  assert.deepEqual(writes, ["latest"]);
  assert.equal(backup(), null);
  assert.equal(controller.getSnapshot().status, "saved");
  controller.dispose();
});

test("publish waits for autosave and uses the latest text without a late draft write", async () => {
  const first = deferred(); const writes = [];
  const { controller } = session(async (value, publish) => { writes.push({ value, publish }); if (writes.length === 1) await first.promise; });
  controller.edit("first");
  const saving = controller.flush();
  controller.edit("final text");
  const publishing = controller.saveExplicit(true);
  assert.equal(writes.length, 1);
  assert.equal(controller.getSnapshot().publishing, true);
  first.resolve();
  await saving; await publishing;
  assert.deepEqual(writes, [{ value: "first", publish: undefined }, { value: "final text", publish: true }]);
  assert.equal(controller.getSnapshot().dirty, false);
  controller.dispose();
});

test("failed drafts keep the recovery copy and retry the newest edits", async () => {
  let fail = true; const writes = [];
  const { controller, backup } = session(async value => { writes.push(value); if (fail) throw new Error("Offline"); });
  controller.edit("draft"); await controller.flush();
  assert.equal(controller.getSnapshot().status, "error");
  assert.equal(backup(), "draft");
  controller.edit("newer draft"); fail = false; await controller.flush();
  assert.deepEqual(writes, ["draft", "newer draft"]);
  assert.equal(backup(), null);
  controller.dispose();
});

test("switching entries cancels scheduled writes and retains recovery", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const writes = [];
  const { controller, backup } = session(async value => { writes.push(value); });
  controller.edit("unfinished"); controller.dispose();
  t.mock.timers.tick(3000); await tick();
  assert.deepEqual(writes, []);
  assert.equal(backup(), "unfinished");
});

test("a response to older text cannot clear recovery for newer text", async () => {
  const first = deferred(); const second = deferred(); let calls = 0;
  const { controller, backup } = session(async () => { await (++calls === 1 ? first.promise : second.promise); });
  controller.edit("old"); const saving = controller.flush();
  controller.edit("new"); first.resolve(); await tick();
  assert.equal(backup(), "new");
  assert.equal(controller.getSnapshot().status, "saving");
  second.resolve(); await saving;
  assert.equal(backup(), null); controller.dispose();
});
