import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the forecast dashboard", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Spielraum/);
  assert.match(html, /SPIELRAUM/);
  assert.match(html, /Bundesliga/);
  assert.match(html, /Teamst.rken/);
  assert.match(html, /Beispieldaten/);
  assert.match(html, /Historische Prognosen/);
  assert.match(html, /Historischen Spieltag ausw.hlen/);
  assert.match(html, /Spieltag 34/);
  assert.match(html, /Ein Blick in die Glaskugel/);
  assert.match(html, /Das Model\. How it works/);
  assert.match(html, /F.r Nerds/);
  assert.match(html, /pitch-art/);
  assert.match(html, /pitch-player/);
  assert.match(html, /pass-line/);
  assert.match(html, /pitch-art__annotations/);
  assert.doesNotMatch(html, /LIVE MODEL SPACE|Ein Pass ist passiert/);
  assert.doesNotMatch(html, /PHASE 03|48\.137|11\.575/);
  assert.match(html, /model-signal__orbit/);
  assert.match(html, /Aktive Policy/);
  assert.match(html, /trend-bars/);
  assert.match(html, /Teamstärken sortieren/);
  assert.match(html, /rank-trend/);
  assert.match(html, /Rang um \d+ Pl.tz(?:e)? (?:verbessert|verschlechtert)/);
  assert.match(html, /Angriff/);
  assert.match(html, /Abwehr/);
  assert.match(html, /↓/);
  assert.doesNotMatch(html, /strength-chart/);
  assert.match(html, /club-mark--circle[^>]*club-mark--bvb/);
  assert.match(html, /club-mark--diamond[^>]*club-mark--svw/);
  assert.doesNotMatch(html, /Keine offiziellen Vereinswappen|Real xG|–/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("server-renders the statistical deep dive", async () => {
  const response = await render("/nerds");
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /Statistical Deep Dive/);
  assert.match(html, /Metropolis/);
  assert.match(html, /Gamma/);
  assert.match(html, /Ranked Probability Score/);
  assert.match(html, /144 historische Pseudospiele/);
  assert.match(html, /0,19797/);
  assert.doesNotMatch(html, /–/);
});
