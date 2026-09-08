import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/", language = "de") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html", cookie: `spielraum-language=${language}` } }),
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
  assert.match(html, /Die Saison im Blick/);
  assert.match(html, /Wie die Prognose entsteht/);
  assert.match(html, /F.r Nerds/);
  assert.match(html, /hero-forecast/);
  assert.match(html, /Spiel im Fokus/);
  assert.match(html, /Duell auf Augenh.he/);
  assert.doesNotMatch(html, /status-chip|Live-Modell/);
  assert.match(html, /1 · Heim/);
  assert.match(html, /X · Remis/);
  assert.match(html, /2 · Gast/);
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
  assert.match(html, /class="club-mark club-mark--small" style="--club-primary:#f0d522"/);
  assert.match(html, /class="club-mark club-mark--small" style="--club-primary:#14824b"/);
  assert.doesNotMatch(html, /\/club-marks\/|club-mark--diamond|club-mark--circle/);
  assert.doesNotMatch(html, /Keine offiziellen Vereinswappen|Real xG|–/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("server-renders English predictions with localised labels and formats", async () => {
  const response = await render("/", "en");
  assert.equal(response.status, 200);
  const html = await response.text();
  const main = html.match(/<main[\s\S]*?<\/main>/)?.[0] ?? "";
  assert.match(html, /<html lang="en"/);
  assert.match(main, /Football at heart/);
  assert.match(main, /Too close to call/);
  assert.match(main, /50,000/);
  assert.match(main, /1 · Home/);
  assert.match(main, /Odds <!-- -->2\.63/);
  assert.match(main, /Rank (?:up|down) \d+ places?/);
  assert.match(main, /Current attack index/);
  assert.match(main, /0\.19797/);
  assert.doesNotMatch(main, /Spieltag|Siegchance|Angriff|Abwehr|Heimsieg|Saisonprognose|0,19797/);
});

test("server-renders English maths and preserves the research citation", async () => {
  const response = await render("/nerds", "en");
  assert.equal(response.status, 200);
  const html = await response.text();
  const main = html.match(/<main[\s\S]*?<\/main>/)?.[0] ?? "";
  assert.match(html, /<html lang="en"/);
  assert.match(main, /What does a model know/);
  assert.match(main, /144 historical pseudo-matches/);
  assert.match(main, /0\.06²/);
  assert.match(main, /ε = 0\.2/);
  assert.match(main, /κ = 0\.10/);
  assert.match(main, /0\.50 = 2\.00/);
  assert.match(main, /10\.1111\/1467-9884\.00243/);
  assert.equal((main.match(/<details class="deep-dive">/g) ?? []).length, 6);
  assert.doesNotMatch(main, /Spieltag|Vorwissen|Abwehr|Saisonprognose|Sommer|Öffnet|0,06/);
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
  assert.match(html, /Was weiß ein Modell/);
  assert.match(html, /https:\/\/doi\.org\/10\.1111\/1467-9884\.00243/);
  assert.match(html, /Prediction and Retrospective Analysis of Soccer Matches in a League/);
  assert.equal((html.match(/<details class="deep-dive">/g) ?? []).length, 6);
  for (const chapter of ["state", "likelihood", "priors", "transition", "inference", "score"]) {
    assert.ok(html.includes(`href="#${chapter}"`));
    assert.ok(html.includes(`id="${chapter}"`));
  }
  assert.match(html, /<caption>Modell und Markt im Vergleich/);
});
