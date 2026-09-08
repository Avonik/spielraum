import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../app/focus-match.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { selectFocusMatch } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const match = (id, probabilities) => ({ id, home: { code: `${id}H`, short: "Heim" }, away: { code: `${id}A`, short: "Gast" }, probabilities });

test("selects a close match beyond the opening fixture without mutating the schedule", () => {
  const fixtures = [match("opening", [0.6, 0.25, 0.15]), match("close", [0.36, 0.3, 0.34])];
  const result = selectFocusMatch(fixtures, []);
  assert.equal(result.item.id, "close");
  assert.equal(result.title, "Duell auf Augenhöhe");
  assert.deepEqual(fixtures.map((item) => item.id), ["opening", "close"]);
});

test("high-confidence favorites take precedence over close matches", () => {
  const result = selectFocusMatch([match("close", [0.36, 0.3, 0.34]), match("clear", [0.1, 0.15, 0.75])], []);
  assert.equal(result.item.id, "clear");
  assert.equal(result.title, "Klare Favoritenrolle");
  assert.match(result.reason, /75 %.*Gast/);
});

test("season underdogs need known rankings and a meaningful match advantage", () => {
  const upset = match("upset", [0.23, 0.25, 0.52]);
  const ranks = [{ club: upset.home, median: 3 }, { club: upset.away, median: 10 }];
  assert.equal(selectFocusMatch([match("clear", [0.8, 0.1, 0.1]), upset], ranks).title, "Außenseiter im Vorteil");
  assert.notEqual(selectFocusMatch([upset], []).title, "Außenseiter im Vorteil");
  assert.notEqual(selectFocusMatch([{ ...upset, probabilities: [0.35, 0.28, 0.37] }], ranks).title, "Außenseiter im Vorteil");
});

test("handles empty schedules, a single fixture and stable ties", () => {
  assert.equal(selectFocusMatch([], []), undefined);
  const first = match("first", [0.5, 0.25, 0.25]);
  assert.equal(selectFocusMatch([first], []).item, first);
  assert.equal(selectFocusMatch([first, match("second", first.probabilities)], []).item, first);
});
