type Match = {
  id: string;
  home: { code: string; short: string };
  away: { code: string; short: string };
  probabilities: [number, number, number];
};

type SeasonPlacement = { club: { code: string }; median: number };

export function selectFocusMatch<T extends Match>(fixtures: T[], placements: SeasonPlacement[]) {
  const ranks = new Map(placements.map((item) => [item.club.code, item.median]));
  const percent = (value: number) => `${Math.round(value * 100)} %`;
  const candidates = fixtures.map((item) => {
    const [home, draw, away] = item.probabilities;
    const gap = Math.abs(home - away);
    const favorite = home >= away ? item.home : item.away;
    const opponent = home >= away ? item.away : item.home;
    const win = Math.max(home, away);
    const favoriteRank = ranks.get(favorite.code);
    const opponentRank = ranks.get(opponent.code);

    // Underdog refers to our season forecast, not reputation or bookmaker odds.
    if (favoriteRank !== undefined && opponentRank !== undefined
      && favoriteRank - opponentRank >= 4 && gap >= 0.08 && win > draw) {
      return { item, score: 3 + gap, title: "Außenseiter im Vorteil",
        reason: `${favorite.short} liegt in unserer Saisonprognose hinter ${opponent.short}, hat in diesem Duell aber mit ${percent(win)} die höchste Siegchance.` };
    }
    if (win >= 0.7) {
      return { item, score: 2 + win, title: "Klare Favoritenrolle",
        reason: `${percent(win)} Siegchance für ${favorite.short}: Unser Modell sieht hier einen klaren Favoriten.` };
    }
    if (gap <= 0.08 && win < 0.5) {
      return { item, score: 1 + (1 - gap), title: "Duell auf Augenhöhe",
        reason: `${item.home.short} bei ${percent(home)}, ${item.away.short} bei ${percent(away)}: Die Siegchancen liegen dicht beieinander. Das wird spannend!` };
    }
    return { item, score: win, title: win > draw && gap >= 0.15 ? "Vorteil für den Favoriten" : "Offener Ausgang",
      reason: win > draw && gap >= 0.15
        ? `${favorite.short} geht mit ${percent(win)} Siegchance ins Spiel. Für ${opponent.short} bleiben ${percent(Math.min(home, away))}, für ein Remis ${percent(draw)}.`
        : `${percent(home)} Heimsieg, ${percent(draw)} Remis, ${percent(away)} Auswärtssieg: Ein Blick auf alle drei Ausgänge lohnt sich.` };
  });
  // Stable ties preserve fixture order; never reorder the dashboard's source data.
  return candidates.reduce<(typeof candidates)[number] | undefined>(
    (best, candidate) => !best || candidate.score > best.score ? candidate : best, undefined,
  );
}
