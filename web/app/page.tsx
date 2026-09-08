"use client";

import { CSSProperties, useEffect, useMemo, useState } from "react";
import { useLanguage, LanguageSwitch } from "./language";
import { selectFocusMatch } from "./focus-match";

type Club = {
  name: string;
  short: string;
  code: string;
  primary: string;
  secondary: string;
  variant: "circle" | "diamond" | "oval" | "shield";
};

type Fixture = {
  id: string;
  kickoff: string;
  home: Club;
  away: Club;
  probabilities: [number, number, number];
};

type HistoryItem = Fixture & {
  season?: string;
  matchday?: number;
  score: [number, number];
  outcome: "H" | "D" | "A";
  hit: boolean;
};

type StrengthTeam = {
  club: Club;
  matchdays: number[];
  attack: number[];
  defense: number[];
};

type StrengthSort = {
  metric: "attack" | "defense";
  direction: "asc" | "desc";
};

type Placement = {
  club: Club;
  median: number;
  range: [number, number];
  title: number;
  top4: number;
  relegation: number;
};

type DashboardData = {
  mode: "preview" | "live";
  generatedAt: string;
  season: string;
  matchday: number;
  fixtures: Fixture[];
  history: HistoryItem[];
  strengths: StrengthTeam[];
  placements: Placement[];
};

const clubs = {
  bayern: club("Bayern München", "Bayern", "FCB", "#d51d32", "#f4efe6", "circle"),
  stuttgart: club("VfB Stuttgart", "Stuttgart", "VFB", "#f1eee7", "#d71832", "shield"),
  elversberg: club("SV Elversberg", "Elversberg", "ELV", "#f1d32f", "#151515", "circle"),
  leverkusen: club("Bayer Leverkusen", "Leverkusen", "B04", "#e52332", "#101010", "shield"),
  koeln: club("1. FC Köln", "Köln", "KOE", "#f4f0e8", "#d31f32", "circle"),
  hoffenheim: club("TSG Hoffenheim", "Hoffenheim", "TSG", "#1b64b0", "#f0eee7", "shield"),
  union: club("Union Berlin", "Union Berlin", "FCU", "#d51d32", "#f5d537", "oval"),
  frankfurt: club("Eintracht Frankfurt", "Frankfurt", "SGE", "#151515", "#e32936", "circle"),
  mainz: club("Mainz 05", "Mainz", "M05", "#df1f37", "#f5f0e7", "circle"),
  paderborn: club("SC Paderborn", "Paderborn", "SCP", "#1768a8", "#161616", "circle"),
  leipzig: club("RB Leipzig", "Leipzig", "RBL", "#f1eee7", "#d51e38", "shield"),
  gladbach: club("Borussia M'gladbach", "M'gladbach", "BMG", "#171717", "#f3efe6", "diamond"),
  dortmund: club("Borussia Dortmund", "Dortmund", "BVB", "#f0d522", "#111111", "circle"),
  hamburg: club("Hamburger SV", "Hamburg", "HSV", "#1767a6", "#f4f0e8", "diamond"),
  freiburg: club("SC Freiburg", "Freiburg", "SCF", "#f3efe7", "#d92035", "oval"),
  bremen: club("Werder Bremen", "Bremen", "SVW", "#14824b", "#f4f0e8", "diamond"),
  augsburg: club("FC Augsburg", "Augsburg", "FCA", "#b62930", "#17754a", "shield"),
  schalke: club("FC Schalke 04", "Schalke", "S04", "#1769ad", "#f3efe7", "circle"),
  heidenheim: club("1. FC Heidenheim", "Heidenheim", "FCH", "#195ba3", "#e72d36", "circle"),
  stpauli: club("FC St. Pauli", "St. Pauli", "STP", "#5b3524", "#f2eee6", "circle"),
  wolfsburg: club("VfL Wolfsburg", "Wolfsburg", "WOB", "#65b32e", "#f2eee6", "circle"),
};

function club(
  name: string,
  short: string,
  code: string,
  primary: string,
  secondary: string,
  variant: Club["variant"],
): Club {
  return { name, short, code, primary, secondary, variant };
}

const previewData: DashboardData = {
  mode: "preview",
  generatedAt: "2026-07-29T12:00:00+02:00",
  season: "2026/27",
  matchday: 1,
  fixtures: [
    fixture("m1", "2026-08-28T20:30:00+02:00", clubs.bayern, clubs.stuttgart, [0.57, 0.23, 0.2]),
    fixture("m2", "2026-08-29T15:30:00+02:00", clubs.elversberg, clubs.leverkusen, [0.17, 0.23, 0.6]),
    fixture("m3", "2026-08-29T15:30:00+02:00", clubs.koeln, clubs.hoffenheim, [0.38, 0.28, 0.34]),
    fixture("m4", "2026-08-29T15:30:00+02:00", clubs.union, clubs.frankfurt, [0.32, 0.29, 0.39]),
    fixture("m5", "2026-08-29T15:30:00+02:00", clubs.mainz, clubs.paderborn, [0.52, 0.27, 0.21]),
    fixture("m6", "2026-08-29T15:30:00+02:00", clubs.leipzig, clubs.gladbach, [0.55, 0.24, 0.21]),
    fixture("m7", "2026-08-29T18:30:00+02:00", clubs.dortmund, clubs.hamburg, [0.63, 0.22, 0.15]),
    fixture("m8", "2026-08-30T15:30:00+02:00", clubs.freiburg, clubs.bremen, [0.46, 0.28, 0.26]),
    fixture("m9", "2026-08-30T17:30:00+02:00", clubs.augsburg, clubs.schalke, [0.43, 0.29, 0.28]),
  ],
  history: [
    history("h1", clubs.heidenheim, clubs.mainz, [0.316, 0.212, 0.472], [0, 2], "A", true),
    history("h2", clubs.leverkusen, clubs.hamburg, [0.724, 0.151, 0.125], [1, 1], "D", false),
    history("h3", clubs.stpauli, clubs.wolfsburg, [0.294, 0.277, 0.428], [1, 3], "A", true),
    history("h4", clubs.gladbach, clubs.hoffenheim, [0.342, 0.256, 0.402], [4, 0], "H", false),
    history("h5", clubs.union, clubs.augsburg, [0.409, 0.252, 0.339], [4, 0], "H", true),
    history("h6", clubs.bremen, clubs.dortmund, [0.249, 0.255, 0.496], [0, 2], "A", true),
  ],
  strengths: [
    strength(clubs.bayern, [76, 78, 81, 82, 84, 86, 89, 88], [65, 67, 68, 71, 73, 74, 76, 78]),
    strength(clubs.dortmund, [68, 69, 72, 71, 74, 76, 75, 84], [58, 59, 61, 63, 62, 64, 66, 69]),
    strength(clubs.leverkusen, [72, 73, 74, 77, 79, 78, 80, 82], [67, 68, 70, 69, 72, 74, 75, 76]),
    strength(clubs.frankfurt, [61, 64, 63, 66, 68, 69, 71, 70], [60, 61, 63, 62, 64, 65, 67, 68]),
  ],
  placements: [
    placement(clubs.bayern, 1, [1, 4], 0.52, 0.83, 0.001),
    placement(clubs.leverkusen, 3, [1, 7], 0.17, 0.59, 0.004),
    placement(clubs.dortmund, 4, [1, 8], 0.14, 0.55, 0.006),
    placement(clubs.leipzig, 5, [2, 10], 0.08, 0.42, 0.018),
    placement(clubs.frankfurt, 6, [3, 11], 0.04, 0.31, 0.026),
    placement(clubs.stuttgart, 7, [3, 13], 0.025, 0.22, 0.05),
  ],
};

function fixture(id: string, kickoff: string, home: Club, away: Club, probabilities: [number, number, number]): Fixture {
  return { id, kickoff, home, away, probabilities };
}

function history(
  id: string,
  home: Club,
  away: Club,
  probabilities: [number, number, number],
  score: [number, number],
  outcome: HistoryItem["outcome"],
  hit: boolean,
): HistoryItem {
  return { ...fixture(id, "2026-05-16T15:30:00+02:00", home, away, probabilities), season: "2025/26", matchday: 34, score, outcome, hit };
}

function strength(clubValue: Club, attack: number[], defense: number[]): StrengthTeam {
  return { club: clubValue, matchdays: attack.map((_, index) => index + 1), attack, defense };
}

function placement(clubValue: Club, median: number, range: [number, number], title: number, top4: number, relegation: number): Placement {
  return { club: clubValue, median, range, title, top4, relegation };
}

function ClubMark({ club: clubValue, size = "normal" }: { club: Club; size?: "small" | "normal" | "large" }) {
  return (
    <span className={`club-mark club-mark--${size}`} style={{ "--club-primary": clubValue.primary } as CSSProperties} aria-hidden="true" />
  );
}

function Probability({ label, value, active }: { label: string; value: number; active?: boolean }) {
  const { t, formatPercent, formatOdds } = useLanguage();
  return (
    <div className={`probability ${active ? "probability--active" : ""}`}>
      <span>{label === "1" ? t("1 · Heim") : label === "X" ? t("X · Remis") : t("2 · Gast")}</span>
      <strong>{formatPercent(value)}</strong>
      <small>{t("Quote ")}{formatOdds(value)}</small>
      <i style={{ "--probability": `${value * 100}%` } as CSSProperties} />
    </div>
  );
}

function MatchCard({ item, featured = false, index = 0 }: { item: Fixture; featured?: boolean; index?: number }) {
  const { t, formatKickoff } = useLanguage();
  const favorite = item.probabilities.indexOf(Math.max(...item.probabilities));
  return (
    <article className={`match-card ${featured ? "match-card--featured" : ""}`} style={{ "--delay": `${index * 55}ms` } as CSSProperties}>
      <div className="match-card__time"><span>{formatKickoff(item.kickoff)}</span>{featured && <span className="match-card__tag">{t("Im Fokus")}</span>}</div>
      <div className="match-card__teams">
        <div className="match-team"><ClubMark club={item.home} size={featured ? "large" : "normal"} /><strong>{item.home.name}</strong><small>{t("Heim")}</small></div>
        <span className="versus">VS</span>
        <div className="match-team match-team--away"><ClubMark club={item.away} size={featured ? "large" : "normal"} /><strong>{item.away.name}</strong><small>{t("Auswärts")}</small></div>
      </div>
      <div className="probability-grid">
        <Probability label="1" value={item.probabilities[0]} active={favorite === 0} />
        <Probability label="X" value={item.probabilities[1]} active={favorite === 1} />
        <Probability label="2" value={item.probabilities[2]} active={favorite === 2} />
      </div>
    </article>
  );
}

function HistoryRow({ item }: { item: HistoryItem }) {
  const { t, formatPercent } = useLanguage();
  const predicted = ["H", "D", "A"][item.probabilities.indexOf(Math.max(...item.probabilities))];
  return (
    <div className="history-row">
      <div className="history-clubs">
        <div><ClubMark club={item.home} size="small" /><span>{item.home.name}</span></div>
        <strong>{item.score[0]} : {item.score[1]}</strong>
        <div><ClubMark club={item.away} size="small" /><span>{item.away.name}</span></div>
      </div>
      <div className="history-prediction">
        <span>{t("Prognose ")}{predicted}</span>
        <strong>{formatPercent(Math.max(...item.probabilities))}</strong>
      </div>
      <span className={`result-pill ${item.hit ? "result-pill--hit" : "result-pill--miss"}`}>{item.hit ? t("Treffer") : t("Überraschung")}</span>
    </div>
  );
}

function TrendBars({ values, matchdays, label, color }: {
  values: number[];
  matchdays: number[];
  label: string;
  color: string;
}) {
  const { t, language, formatIndex } = useLanguage();
  const [inspectedIndex, setInspectedIndex] = useState<number | null>(null);
  const activeIndex = inspectedIndex !== null && inspectedIndex < values.length
    ? inspectedIndex
    : values.length - 1;
  if (values.length === 0) return <p className="trend-chart__empty">{t("Noch keine Werte vorhanden.")}</p>;

  return (
    <div className="trend-chart" style={{ "--trend-color": color, "--trend-width": `${values.length * 30 - 6}px` } as CSSProperties}>
      <div className="trend-chart__readout" role="status" aria-live="polite" aria-atomic="true">
        <span>{t("Vor Spieltag ")}{matchdays[activeIndex] ?? activeIndex + 1}</span>
        <strong>{label} {formatIndex(values[activeIndex])}</strong>
      </div>
      <div className="trend-chart__scroll">
        <div className="trend-bars" role="group" aria-label={`${label} ${language === "de" ? "nach Spieltag" : "by matchday"}`}>
          {values.map((value, index) => (
            <button
              type="button"
              className={`trend-bar ${index === activeIndex ? "trend-bar--active" : ""}`}
              key={`${matchdays[index] ?? index}-${index}`}
              aria-label={`${label}, ${language === "de" ? "vor Spieltag" : "before matchday"} ${matchdays[index] ?? index + 1}: ${formatIndex(value)}`}
              onMouseEnter={() => setInspectedIndex(index)}
              onFocus={() => setInspectedIndex(index)}
              onClick={() => setInspectedIndex(index)}
            >
              <span className="trend-bar__fill" style={{ height: `${Math.max(0, Math.min(100, value))}%` }} />
            </button>
          ))}
        </div>
        <div className="trend-chart__range" aria-hidden="true">
          <span>{t("ST ")}{matchdays[0] ?? 1}</span>
          {values.length > 1 && <span>{t("ST ")}{matchdays[values.length - 1] ?? values.length}</span>}
        </div>
      </div>
    </div>
  );
}

function RankTrend({ change }: { change: number | undefined }) {
  const { language } = useLanguage();
  if (!change) return null;
  const improved = change > 0;
  const label = language === "en"
    ? `Rank ${improved ? "up" : "down"} ${Math.abs(change)} ${Math.abs(change) === 1 ? "place" : "places"}`
    : improved
    ? `Rang um ${change} ${change === 1 ? "Platz" : "Plätze"} verbessert`
    : `Rang um ${Math.abs(change)} ${change === -1 ? "Platz" : "Plätze"} verschlechtert`;
  return <span className={`rank-trend rank-trend--${improved ? "up" : "down"}`} aria-label={label} title={label}>{improved ? "↗" : "↘"}</span>;
}

function strengthRankChanges(strengths: StrengthTeam[], metric: StrengthSort["metric"]) {
  const comparable = strengths.filter((item) => item[metric].length >= 2);
  const ranksAt = (offset: number) => {
    const ranked = [...comparable].sort((left, right) => {
      const difference = (right[metric].at(offset) ?? 0) - (left[metric].at(offset) ?? 0);
      return difference || left.club.name.localeCompare(right.club.name, "de");
    });
    const ranks = new Map<string, number>();
    let lastValue: number | undefined;
    let rank = 0;
    ranked.forEach((item, index) => {
      const value = item[metric].at(offset) ?? 0;
      if (lastValue === undefined || value !== lastValue) rank = index + 1;
      ranks.set(item.club.code, rank);
      lastValue = value;
    });
    return ranks;
  };
  const current = ranksAt(-1);
  const previous = ranksAt(-2);
  return new Map(comparable.map((item) => [
    item.club.code,
    (previous.get(item.club.code) ?? 0) - (current.get(item.club.code) ?? 0),
  ]));
}

export default function Home() {
  const { t, language, formatPercent, formatIndex, formatTimestamp, formatRank, formatRange } = useLanguage();
  const [data, setData] = useState(previewData);
  const focus = useMemo(() => selectFocusMatch(data.fixtures, data.placements, language), [data.fixtures, data.placements, language]);
  const [historyFilter, setHistoryFilter] = useState<"all" | "hit" | "miss">("all");
  const [selectedHistoryKey, setSelectedHistoryKey] = useState<string | null>(null);
  const [selectedStrengthCode, setSelectedStrengthCode] = useState<string | null>(null);
  const [strengthSort, setStrengthSort] = useState<StrengthSort>({ metric: "attack", direction: "desc" });

  useEffect(() => {
    let disposed = false;
    const controllers = new Set<AbortController>();
    const refresh = () => {
      const controller = new AbortController();
      controllers.add(controller);
      fetch("/api/dashboard", { signal: controller.signal, cache: "no-store" })
        .then((response) => (response.ok ? response.json() : Promise.reject()))
        .then((payload: DashboardData) => {
          if (!disposed) setData(payload);
        })
        .catch(() => undefined)
        .finally(() => controllers.delete(controller));
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    refresh();
    const interval = window.setInterval(refresh, 5 * 60 * 1000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      disposed = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      controllers.forEach((controller) => controller.abort());
    };
  }, []);

  const historyGroups = useMemo(() => {
    const groups = new Map<string, { key: string; season?: string; matchday?: number; items: HistoryItem[] }>();
    data.history.forEach((item) => {
      const season = item.season ?? data.season;
      const matchday = item.matchday ?? Math.max(1, data.matchday - 1);
      const key = `${season}:${matchday}`;
      const group = groups.get(key) ?? { key, season, matchday, items: [] };
      group.items.push(item);
      groups.set(key, group);
    });
    return [...groups.values()];
  }, [data.history, data.matchday, data.season]);
  const activeHistoryKey = historyGroups.some((group) => group.key === selectedHistoryKey)
    ? selectedHistoryKey
    : historyGroups[0]?.key ?? null;
  const activeHistoryIndex = historyGroups.findIndex((group) => group.key === activeHistoryKey);
  const activeHistoryGroup = historyGroups[activeHistoryIndex];
  const filteredHistory = useMemo(() => (activeHistoryGroup?.items ?? []).filter((item) => {
    if (historyFilter === "hit") return item.hit;
    if (historyFilter === "miss") return !item.hit;
    return true;
  }), [activeHistoryGroup, historyFilter]);
  const sortedStrengths = useMemo(() => [...data.strengths].sort((left, right) => {
    const leftValue = left[strengthSort.metric].at(-1) ?? 0;
    const rightValue = right[strengthSort.metric].at(-1) ?? 0;
    const difference = leftValue - rightValue;
    if (difference === 0) return left.club.name.localeCompare(right.club.name, "de");
    return strengthSort.direction === "desc" ? -difference : difference;
  }), [data.strengths, strengthSort]);
  const rankChanges = useMemo(
    () => strengthRankChanges(data.strengths, strengthSort.metric),
    [data.strengths, strengthSort.metric],
  );
  const selectedStrength = data.strengths.find((item) => item.club.code === selectedStrengthCode) ?? sortedStrengths[0];
  const selectedStrengthValue = selectedStrength?.[strengthSort.metric].at(-1);

  const toggleStrengthSort = (metric: StrengthSort["metric"]) => {
    setStrengthSort((current) => current.metric === metric
      ? { metric, direction: current.direction === "desc" ? "asc" : "desc" }
      : { metric, direction: "desc" });
  };

  return (
    <main>
      <a className="skip-link" href="#spieltag">{t("Zu den Prognosen")}</a>
      <header className="site-header">
        <a className="brand" href="#top" aria-label={t("Spielraum Startseite")}>
          <span className="brand-mark"><i /><i /><i /></span>
          <span>SPIELRAUM<small>Forecast Lab</small></span>
        </a>
        <nav aria-label={t("Hauptnavigation")}>
          <a href="#spieltag">{t("Spieltag")}</a><a href="#historie">{t("Historie")}</a><a href="#staerken">{t("Teamstärken")}</a><a href="#tabelle">{t("Saisonprognose")}</a><a href="#modell">{t("Modell")}</a>
        </nav>
        <LanguageSwitch />
      </header>

      <section className="hero" id="top">
        <div className="hero__copy">
          <div className="eyebrow"><span className="season-label">Bundesliga {data.season}</span>{t(" Spieltag ")}{data.matchday}</div>
          <h1>{t("Fußball im Bauch.")}<br /><em>{t("Daten im Kopf.")}</em></h1>
          <p>{t("Dein Spieltag in Wahrscheinlichkeiten. Entdecke faire Quoten und verfolge die Form deines Teams.")}</p>
          <a className="hero-link" href="#spieltag">{t("Zu den Spieltagsprognosen ")}<span aria-hidden="true">↗</span></a>
          <div className="hero__meta"><span><b>1 X 2?</b>{t(" Alle Prognosen vor Anpfiff")}</span><span><b>{t("50.000+")}</b>{t(" Saison-Simulationen")}</span><span><b>{t("jeden Spieltag neu")}</b>{t("ein Modell, das mitwächst")}</span></div>
        </div>
        <aside className="hero-forecast" aria-label={t("Spiel im Fokus")}>
          <div className="hero-forecast__heading"><span>{t("Spiel im Fokus")}</span><span>{data.mode === "preview" ? t("Beispieldaten") : t("Modellprognose")}</span></div>
          {focus ? <>
            <MatchCard item={focus.item} featured />
            <div className="focus-story"><strong>{focus.title}</strong><p>{focus.reason}</p></div>
          </> : <div className="fixture-empty">{t("Die nächsten Begegnungen erscheinen, sobald der Spielplan verfügbar ist.")}</div>}
          <p>{t("1 = Heimsieg · X = Unentschieden · 2 = Auswärtssieg")}</p><p>{t("Alle Anstoßzeiten: Europe/Berlin")}</p>
        </aside>
      </section>

      <section className="section matchday-section" id="spieltag">
        <div className="section-heading">
          <div><div><div className="eyebrow">{t("Die weiteren Begegnungen · ")}{data.season}</div><h2>{t("Spieltag ")}{data.matchday}<span className="heading-accent">.</span></h2></div></div>
          <div className="data-stamp"><span>{t("Datenstand")}</span><strong>{formatTimestamp(data.generatedAt)}</strong><small>{data.mode === "preview" ? t("Beispieldaten. Produktiver Snapshot folgt") : t("Schau wo dein Team steht")}</small></div>
        </div>
        <div className="match-grid">{data.fixtures.filter((item) => item.id !== focus?.item.id).map((item, index) => <MatchCard item={item} index={index} key={item.id} />)}</div>
        <p className="fair-note"><span>i</span>{t(" Faire Quote = 1 ÷ Modellwahrscheinlichkeit. Ohne Buchmachermarge, keine Wettberatung.")}</p>
      </section>

      <section className="section history-section" id="historie">
        <div className="section-heading section-heading--compact">
          <div><div><div className="eyebrow">{t("Historische Prognosen")}</div><h2>{t("Nach dem Abpfiff.")}</h2>{data.history.length > 0 && <div className="matchday-switcher matchday-switcher--heading" aria-label={t("Historischen Spieltag auswählen")}>
            <button type="button" aria-label={t("Vorheriger Spieltag")} disabled={activeHistoryIndex >= historyGroups.length - 1} onClick={() => setSelectedHistoryKey(historyGroups[activeHistoryIndex + 1]?.key ?? activeHistoryKey)}>←</button>
            <div><strong>{activeHistoryGroup?.matchday ? `${t("Spieltag")} ${activeHistoryGroup.matchday}` : t("Archiv")}</strong>{activeHistoryGroup?.season && <small>{activeHistoryGroup.season}</small>}</div>
            <button type="button" aria-label={t("Nächster Spieltag")} disabled={activeHistoryIndex <= 0} onClick={() => setSelectedHistoryKey(historyGroups[activeHistoryIndex - 1]?.key ?? activeHistoryKey)}>→</button>
          </div>}</div></div>
          {data.history.length > 0 && <div className="history-controls">
            <div className="segmented-control" aria-label={t("Historie filtern")}>
              {(["all", "hit", "miss"] as const).map((filter) => <button type="button" className={historyFilter === filter ? "active" : ""} aria-pressed={historyFilter === filter} onClick={() => setHistoryFilter(filter)} key={filter}>{filter === "all" ? t("Alle") : filter === "hit" ? t("Treffer") : t("Überraschungen")}</button>)}
            </div>
          </div>}
        </div>
        {data.history.length === 0 ? (
          <div className="history-empty">
            <span>{t("NOCH LEER")}</span>
            <div><strong>{t("Noch keine abgeschlossenen Live-Prognosen.")}</strong><p>{t("Die erste Prognose für Spieltag 1 ist veröffentlicht. Nach Abpfiff erscheinen hier das Ergebnis und genau die Wahrscheinlichkeiten, die vorher festgeschrieben wurden.")}</p></div>
          </div>
        ) : filteredHistory.length > 0 ? (
          <div className="history-list">{filteredHistory.map((item) => <HistoryRow item={item} key={item.id} />)}</div>
        ) : (
          <div className="history-empty">
            <span>{t("KEINE TREFFER")}</span>
            <div><strong>{t("Für diesen Filter gibt es an diesem Spieltag keine Spiele.")}</strong><p>{t("Wähle einen anderen Filter oder schalte zu einem anderen verfügbaren Spieltag.")}</p></div>
          </div>
        )}
        <div className="immutable-note"><span>{t("Wir bleiben transparent")}</span><p>{t("Jede Prognose kannst du einsehen. Die ursprüngliche Prognose bleibt unverändert.")}</p></div>
      </section>

      <section className="section strength-section" id="staerken">
        <div className="section-heading">
          <div><div><div className="eyebrow">{t("Dynamische Teamstärken")}</div><h2>{t("Die Form dahinter.")}</h2>{data.mode === "preview" && <span className="preview-label">Illustrative Preview</span>}</div></div>
          <p className="section-intro">{t("Angriff und Abwehr entwickeln sich getrennt. Jeden Spieltag werden die Stärken neu geschätzt. Wo steht dein Team?")}</p>
        </div>
        <div className="strength-panel">
          <div className="strength-picker">
            <div className="strength-sort" aria-label={t("Teamstärken sortieren")}>
              {(["attack", "defense"] as const).map((metric) => {
                const active = strengthSort.metric === metric;
                const label = metric === "attack" ? t("Angriff") : t("Abwehr");
                return <button type="button" className={active ? "active" : ""} aria-pressed={active} onClick={() => toggleStrengthSort(metric)} key={metric}><span>{label}</span><b aria-hidden="true">{active ? strengthSort.direction === "desc" ? "↓" : "↑" : ""}</b></button>;
              })}
            </div>
            {sortedStrengths.map((item) => <button type="button" key={item.club.code} className={item.club.code === selectedStrength?.club.code ? "active" : ""} aria-pressed={item.club.code === selectedStrength?.club.code} onClick={() => setSelectedStrengthCode(item.club.code)}><ClubMark club={item.club} size="small" /><span className="strength-team-name">{item.club.name}<RankTrend change={rankChanges.get(item.club.code)} /></span><b>{formatIndex(item[strengthSort.metric].at(-1))}</b></button>)}
          </div>
          {selectedStrength && <div className="strength-detail">
            <div className="strength-title"><ClubMark club={selectedStrength.club} size="large" /><div><small>{language === "en" ? `Current ${strengthSort.metric === "attack" ? "attack" : "defence"} index` : `Aktueller ${strengthSort.metric === "attack" ? "Angriffs" : t("Abwehr")}index`}</small><h3>{selectedStrength.club.name}</h3></div><strong>{formatIndex(selectedStrengthValue)}</strong></div>
            <div className="trend-row"><div><span className="legend-dot legend-dot--attack" />{t("Angriff ")}<b>{formatIndex(selectedStrength.attack.at(-1))}</b></div><TrendBars key={`${selectedStrength.club.code}-attack`} values={selectedStrength.attack} matchdays={selectedStrength.matchdays} label={t("Angriff")} color="var(--attack)" /></div>
            <div className="trend-row"><div><span className="legend-dot legend-dot--defense" />{t("Abwehr ")}<b>{formatIndex(selectedStrength.defense.at(-1))}</b></div><TrendBars key={`${selectedStrength.club.code}-defense`} values={selectedStrength.defense} matchdays={selectedStrength.matchdays} label={t("Abwehr")} color="var(--defense)" /></div>
          </div>}
        </div>
      </section>

      <section className="section placements-section" id="tabelle">
        <div className="section-heading">
          <div><div><div className="eyebrow">{t("50.000 Saison-Simulationen")}</div><h2>{t("Die Saison im Blick.")}</h2>{data.mode === "preview" && <span className="preview-label">Illustrative Preview</span>}</div></div>
          <p className="section-intro">{t("Auch wir haben keine Glaskugel, aber wir können die Verteilung möglicher Endplatzierungen simulieren. Gerade früh in der Saison ist Unsicherheit aber hoch, deshalb lieben wir Fußball")}</p>
        </div>
        <div className="placement-table" role="region" aria-label={t("Saisonprognose, auf kleinen Bildschirmen horizontal scrollbar")} tabIndex={0}>
          <div className="placement-head"><span>Team</span><span>Median</span><span>{t("80-%-Bereich")}</span><span>{t("Meister")}</span><span>Top 4</span><span>{t("Abstieg")}</span></div>
          {data.placements.map((item, index) => <div className="placement-row" key={item.club.code} style={{ "--delay": `${index * 70}ms` } as CSSProperties}>
            <div><ClubMark club={item.club} size="small" /><strong>{item.club.name}</strong></div><b>{formatRank(item.median)}</b>
            <div className="range-track"><i style={{ left: `${(item.range[0] - 1) / 17 * 100}%`, width: `${(item.range[1] - item.range[0] + 1) / 18 * 100}%` }} /><span>{formatRange(...item.range)}</span></div>
            <span>{formatPercent(item.title)}</span><span>{formatPercent(item.top4)}</span><span className={item.relegation > 0.1 ? "danger" : ""}>{formatPercent(item.relegation)}</span>
          </div>)}
        </div>
      </section>

      <section className="section model-section" id="modell">
        <div className="section-heading">
          <div><div><div className="eyebrow">{t("Das Modell")}</div><h2>{t("Wie die Prognose entsteht.")}</h2></div></div>
          <a className="nerd-link" href="/nerds">{t("Für Nerds ")}<span>Statistical Deep Dive</span></a>
        </div>
        <div className="model-showcase">
          <aside className="model-signal" aria-label={t("Animierte Darstellung der aktiven Modell-Policy")}>
            <div className="model-signal__orbit"><span>V2</span><i /><i /><i /></div>
            <div><small>{t("Aktive Policy")}</small><strong>Carry → Fresh</strong><p>{t("Mischung aus Vorsaison und aktueller Saison")}</p></div>
          </aside>
          <div className="mechanics-grid">
            <article><h3>{t("Erfahrung")}</h3><p>{t("Das Modell nutzt Wissen aus vergangenen Saisons um Teams besser einzuschätzen.")}</p><div className="mini-policy"><i /><i /><i /><i /><i /></div></article>
            <article><h3>{t("Gegenwart")}</h3><p>{t("Mit jedem neuen Spiel gewinnt die aktuelle Saison an Gewicht. Vergangene Stärke tritt Schritt für Schritt zurück.")}</p><div className="fresh-pulse"><i /><i /><i /></div></article>
            <article><h3>{t("Spielqualität")}</h3><p>{t("Das Modell schaut tiefer als nur auf Sieg oder Niederlage und trennt nachhaltige Leistung von kurzfristigem Ergebnisglück.")}</p><div className="signal-flow">{[18, 42, 28, 66, 38, 82, 54].map((v, i) => <i style={{ height: `${v}%` }} key={i} />)}</div></article>
          </div>
        </div>
        <div className="backtest-card">
          <div><div className="eyebrow">{t("Wir gegen die Buchmacher · 2010/11-2025/26")}</div><h3>{t("Nah am Markt. ")}</h3><p>{t("Der RPS misst die Qualität der vollständigen 1-X-2-Verteilung. Niedriger ist besser.")}</p></div>
          <div className="backtest-bars"><div><span>{t("Unser V2")}</span><i><b style={{ width: "97%" }} /></i><strong>{t("0,19797")}</strong></div><div><span>{t("Buchmacher")}</span><i><b style={{ width: "94%" }} /></i><strong>{t("0,19204")}</strong></div><small>{t("Relativer Abstand: 3,1 %")}</small></div>
        </div>
      </section>

      <footer>
        <a className="brand" href="#top"><span className="brand-mark"><i /><i /><i /></span><span>SPIELRAUM<small>Forecast Lab</small></span></a>
        <p>{t("Ein unabhängiges Portfolio-Projekt über probabilistische Fußballprognosen. Wahrscheinlichkeiten sind keine Gewissheiten. Genau das macht sie interessant.")}</p>
        <div><span>{t("Modell V2.1")}</span><span>Bayesian</span><span>Pi powered</span><a href="https://github.com/Avonik/spielraum" target="_blank" rel="noopener noreferrer">GitHub ↗</a><a href="https://juhermes.de/" target="_blank" rel="noopener noreferrer">juhermes.de ↗</a></div>
      </footer>
    </main>
  );
}
