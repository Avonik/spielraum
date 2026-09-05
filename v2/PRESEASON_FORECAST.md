# Preseason-Forecast und Saisonübergang

Stand: 29. Juli 2026.

## Produktionsmodell

Die Forecast-Policy führt zwei strukturell identische Real-xG-V2-Streams:

1. `carry_v2` kombiniert den V2-Endposterior der Vorsaison mit dem
   leak-freien Kaderwertprior der neuen Saison.
2. `fresh_v2` verwendet nur den Kaderwertprior und die laufende Saison.

Beide Streams nutzen kontinuierliches Understat-xG, die Gamma-Likelihood und
dieselben V2-Hyperparameter. Der einzige Unterschied ist der Vorjahresposterior.

Das globale Heim-/Auswärts-xG-Niveau wird nicht mehr aus den ersten ein oder
zwei Saisonspielen geschätzt. Historische Ligawerte wirken wie 144
Pseudospiele und werden mit den laufenden Saisondaten gewichtet.

Die empfohlene Ergebnisprognose ist:

- bis einschließlich Spieltag 12: 100 % `carry_v2`;
- Spieltag 13–17: Cosine-Fade von Carry zu Fresh;
- ab Spieltag 18: 100 % `fresh_v2`.

`run_dual_v2_season` verwendet die 144 Pseudospiele standardmäßig und schreibt
die fertige Policy direkt als `p_home_recommended_v2`,
`p_draw_recommended_v2`, `p_away_recommended_v2` und
`rps_recommended_v2`. `carry_weight_recommended` dokumentiert das verwendete
Gewicht pro Spiel.

## Backtest-Ergebnis

Über elf Saisons erreicht der robuste Default RPS 0,20559 gegenüber 0,19892
beim Buchmacher. Das sind 3,35 % Rückstand. Der vorherige identische Ansatz
ohne stabilisiertes Ligalevel lag bei 0,21012.

Im High-Budget-Test 2023/24–2025/26 erreicht der robuste Default ungefähr
0,19797 gegenüber 0,19204 beim Buchmacher, also rund 3,1 % Rückstand. Das
deskriptive Optimum liegt mit 0,19783 nur 0,00014 besser.

Die Verbesserung gegenüber dem alten Ansatz beträgt über elf Saisons 0,00453
RPS. Das saison-geclusterte 95-%-Bootstrap-Intervall reicht von 0,00237 bis
0,00677; neun von elf Saisons verbessern sich.

## Reproduzieren

```powershell
uv run python v2/early_season_level_experiments.py --budget confirm --workers 2
uv run python v2/season_transition_experiments.py `
  --budget confirm --summer-scales 1.0 --workers 2 `
  --goal-level-prior-matches 144
```

Vollständige Methodik und historische Zwischenstände stehen in
[`PRESEASON_EXPERIMENT_RESULTS.md`](PRESEASON_EXPERIMENT_RESULTS.md).
