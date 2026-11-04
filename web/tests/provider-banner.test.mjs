import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import ts from "typescript";

const asModule = (source) => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const source = await readFile(new URL("../app/provider-banner.tsx", import.meta.url), "utf8");
const dictionary = await readFile(new URL("../app/translations.ts", import.meta.url), "utf8");
const { english } = await import(asModule(ts.transpileModule(dictionary, {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText));

async function render(status, language = "de") {
  const languageMock = asModule(`export const useLanguage = () => ({ t: (text) => ${language === "en" ? "(" + JSON.stringify(english) + ")[text] ?? text" : "text"} });`);
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX },
  }).outputText.replace('"./language"', JSON.stringify(languageMock))
    .replace('"react/jsx-runtime"', JSON.stringify(import.meta.resolve("react/jsx-runtime")));
  const { ProviderBanner } = await import(asModule(compiled));
  return renderToStaticMarkup(createElement(ProviderBanner, { status }));
}

test("shows the outage notice in German and English", async () => {
  const de = await render({ available: false });
  assert.match(de, /role="status"/);
  assert.match(de, /Understat-API derzeit nicht verfügbar/);
  assert.match(de, /zuletzt veröffentlichten Prognosen/);
  const en = await render({ available: false }, "en");
  assert.match(en, /Understat API is currently unavailable/);
  assert.match(en, /last published forecasts/);
});

test("hides the notice after recovery and before the first check", async () => {
  for (const status of [{ available: true }, null, undefined]) {
    assert.doesNotMatch(await render(status), /provider-banner|Understat/);
  }
});
