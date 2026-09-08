import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const asModule = (source) => `data:text/javascript;base64,${Buffer.from(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText).toString("base64")}`;
const dictionaryUrl = asModule(await readFile(new URL("../app/translations.ts", import.meta.url), "utf8"));
const localeSource = await readFile(new URL("../app/locale.ts", import.meta.url), "utf8");
const { createFormatting, translate } = await import(asModule(localeSource.replace('"./translations"', JSON.stringify(dictionaryUrl))));
const { english } = await import(dictionaryUrl);

test("uses each language's decimal, percent, odds and rank conventions", () => {
  const de = createFormatting("de");
  const en = createFormatting("en");
  assert.equal(de.formatPercent(0.388), "38,8 %");
  assert.equal(en.formatPercent(0.388), "38.8%");
  assert.equal(de.formatOdds(0.5), "2,00");
  assert.equal(en.formatOdds(0.5), "2.00");
  assert.equal(en.formatIndex(72.4), "72.4");
  assert.equal(en.formatIndex(undefined), "-");
  assert.equal(de.formatRange(2, 11), "2. bis 11.");
  assert.equal(en.formatRange(2, 11), "2 to 11");
  assert.equal(en.formatRank(2), "2");
});

test("localises dates while keeping Berlin time through summer and winter", () => {
  const en = createFormatting("en");
  const de = createFormatting("de");
  assert.match(en.formatKickoff("2026-08-28T18:30:00Z"), /Fri.*28 Aug.*20:30/);
  assert.match(en.formatKickoff("2026-12-04T19:30:00Z"), /Fri.*04 Dec.*20:30/);
  assert.match(de.formatTimestamp("2026-09-06T18:16:00Z"), /September 2026.*20:16/);
  assert.match(en.formatTimestamp("2026-07-29T10:00:00Z"), /29 July 2026 at 12:00/);
});

test("preserves spacing around inline translations and original German copy", () => {
  assert.equal(translate("en", " und "), " and ");
  assert.equal(translate("de", " und "), " und ");
  assert.equal(translate("en", "SPIELRAUM"), "SPIELRAUM");
});

test("all explicit translation calls have an English entry", async () => {
  for (const path of ["../app/page.tsx", "../app/nerds/nerds-content.tsx"]) {
    const source = await readFile(new URL(path, import.meta.url), "utf8");
    const ast = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    function visit(node) {
      if (ts.isCallExpression(node) && node.expression.getText(ast) === "t" && ts.isStringLiteral(node.arguments[0])) {
        assert.ok(Object.hasOwn(english, node.arguments[0].text.trim()), `Missing translation: ${node.arguments[0].text}`);
      }
      ts.forEachChild(node, visit);
    }
    visit(ast);
  }
});
