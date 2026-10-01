import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../lib/ptgotw-ranking.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const ranking = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("moves one writeup while preserving the order of every other writeup", () => {
  assert.deepEqual(ranking.moveRanking([1, 2, 3, 4], 3, 1), [1, 4, 2, 3]);
  assert.deepEqual(ranking.moveRanking([1, 2, 3, 4], 0, 3), [2, 3, 4, 1]);
});

test("out-of-range moves cannot lose a writeup", () => {
  assert.deepEqual(ranking.moveRanking([1, 2, 3], 0, -1), [1, 2, 3]);
  assert.deepEqual(ranking.moveRanking([1, 2, 3], 2, 3), [1, 2, 3]);
});

test("formats ordinal placements including teen exceptions", () => {
  assert.equal(ranking.ordinal(1), "1st");
  assert.equal(ranking.ordinal(2), "2nd");
  assert.equal(ranking.ordinal(3), "3rd");
  assert.equal(ranking.ordinal(11), "11th");
  assert.equal(ranking.ordinal(12), "12th");
});

test("only the top five positions score", () => {
  assert.deepEqual(Array.from({ length: 12 }, (_, index) => ranking.pointsForPosition(index + 1)), [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, 0]);
});

test("formats admin deadline inputs in America/Chicago", () => {
  assert.equal(ranking.chicagoDateTimeLocal("2026-10-02T12:30:00Z"), "2026-10-02T07:30");
  assert.equal(ranking.chicagoDateTimeLocal("2026-12-02T13:30:00Z"), "2026-12-02T07:30");
});
