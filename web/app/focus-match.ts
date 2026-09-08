type Match = {
  id: string;
  home: { code: string; name: string };
  away: { code: string; name: string };
  probabilities: [number, number, number];
};

type SeasonPlacement = { club: { code: string }; median: number };

export function selectFocusMatch<T extends Match>(fixtures: T[], placements: SeasonPlacement[], language: "de" | "en" = "de") {
  const en = language === "en";
  const ranks = new Map(placements.map((item) => [item.club.code, item.median]));
  const percent = (value: number) => `${Math.round(value * 100)}${en ? "" : " "}%`;
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
      return { item, score: 3 + gap, title: en ? "The underdog has the edge" : "Außenseiter im Vorteil",
        reason: en ? `${favorite.name} trails ${opponent.name} in our season forecast, but has the highest chance of winning this match at ${percent(win)}.` : `${favorite.name} liegt in unserer Saisonprognose hinter ${opponent.name}, hat in diesem Duell aber mit ${percent(win)} die höchste Siegchance.` };
    }
    if (win >= 0.7) {
      return { item, score: 2 + win, title: en ? "A clear favourite" : "Klare Favoritenrolle",
        reason: en ? `A ${percent(win)} chance of victory for ${favorite.name}: our model sees a clear favourite here.` : `${percent(win)} Siegchance für ${favorite.name}: Unser Modell sieht hier einen klaren Favoriten.` };
    }
    if (gap <= 0.08 && win < 0.5) {
      return { item, score: 1 + (1 - gap), title: en ? "Too close to call" : "Duell auf Augenhöhe",
        reason: en ? `${item.home.name} at ${percent(home)}, ${item.away.name} at ${percent(away)}: their win probabilities are closely matched. This could be a tight one!` : `${item.home.name} bei ${percent(home)}, ${item.away.name} bei ${percent(away)}: Die Siegchancen liegen dicht beieinander. Das wird spannend!` };
    }
    return { item, score: win, title: win > draw && gap >= 0.15 ? (en ? "The favourite has the edge" : "Vorteil für den Favoriten") : (en ? "An open contest" : "Offener Ausgang"),
      reason: en ? (win > draw && gap >= 0.15
        ? `${favorite.name} goes into the match with a ${percent(win)} chance of winning. ${opponent.name} has ${percent(Math.min(home, away))}, with ${percent(draw)} for a draw.`
        : `${percent(home)} home win, ${percent(draw)} draw, ${percent(away)} away win: all three outcomes deserve a closer look.`) : win > draw && gap >= 0.15
        ? `${favorite.name} geht mit ${percent(win)} Siegchance ins Spiel. Für ${opponent.name} bleiben ${percent(Math.min(home, away))}, für ein Remis ${percent(draw)}.`
        : `${percent(home)} Heimsieg, ${percent(draw)} Remis, ${percent(away)} Auswärtssieg: Ein Blick auf alle drei Ausgänge lohnt sich.` };
  });
  // Stable ties preserve fixture order; never reorder the dashboard's source data.
  return candidates.reduce<(typeof candidates)[number] | undefined>(
    (best, candidate) => !best || candidate.score > best.score ? candidate : best, undefined,
  );
}
