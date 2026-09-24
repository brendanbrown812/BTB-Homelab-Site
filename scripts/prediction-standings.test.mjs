import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../lib/prediction-standings.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { rankPredictionStandings } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("screenshot records receive competition ranks and both leaders rank first", () => {
  const rows = [
    ["Martin", 8, 4], ["Diesel", 8, 4], ["Bill", 5, 7], ["Joey", 5, 7],
    ["Brendan", 5, 7], ["Nate", 0, 12], ["Conman", 0, 12],
  ].map(([name, wins, losses]) => ({ name, wins, losses, pushes: 0 }));
  const ranked = rankPredictionStandings(rows);
  assert.deepEqual(ranked.map(row => row.rankLabel), ["T1", "T1", "T3", "T3", "T3", "T6", "T6"]);
  assert.deepEqual(ranked.filter(row => row.rank === 1).map(row => row.name), ["Martin", "Diesel"]);
});

test("unique ranks remain numeric, identical records are grouped, and input is untouched", () => {
  const rows = [
    { name: "A", wins: 3, losses: 2, pushes: 1 },
    { name: "B", wins: 5, losses: 1, pushes: 0 },
    { name: "C", wins: 3, losses: 3, pushes: 0 },
    { name: "D", wins: 3, losses: 2, pushes: 1 },
    { name: "E", wins: 3, losses: 2, pushes: 0 },
  ];
  const original = structuredClone(rows);
  const ranked = rankPredictionStandings(rows);
  assert.deepEqual(ranked.map(row => [row.name, row.rankLabel]), [["B", "1"], ["A", "T2"], ["D", "T2"], ["E", "4"], ["C", "5"]]);
  assert.deepEqual(rows, original);
  assert.deepEqual(rankPredictionStandings([]), []);
  assert.equal(rankPredictionStandings([rows[0]])[0].rankLabel, "1");
});
