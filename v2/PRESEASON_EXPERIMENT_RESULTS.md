# Saisonübergang: Experimente und Empfehlung

## Update 29. Juli 2026: stabilisiertes Ligalevel

Die große Frühphasenlücke hatte eine konkrete technische Ursache: Nach dem
ersten Freitagsspiel wurde das globale Heim-/Auswärts-xG-Niveau aus genau
diesem einen Spiel neu geschätzt. Dadurch entstanden am Samstag teilweise
80–99-%-Prognosen für Auswärtssiege. Der Vorjahres-Carry war nicht die
Hauptursache.

Der korrigierte Filter verwendet für beide V2-Streams 144 historische
Pseudospiele für das globale Ligalevel. Aktuelle Saisondaten überschreiben
dieses Signal mit wachsender Stichprobe. Alle Tests verwenden echtes
Understat-xG und sind leak-frei.

### Spieltag 1–5, 11 Saisons

| Variante | RPS |
|---|---:|
| Buchmacher | **0,19231** |
| Carry V2, 144 historische Pseudospiele | **0,20426** |
| Carry V2, altes instabiles Ligalevel | 0,23269 |
| Fresh V2, altes instabiles Ligalevel | 0,23813 |

Der 144er-Prior verbessert Carry um 0,02842 RPS und gewinnt in zehn von elf
Saisons. Das saison-geclusterte 95-%-Bootstrap-Intervall beträgt 0,01515 bis
0,04228.

### Ganze Saison

Der robuste Produktionsdefault nutzt Carry vollständig bis Spieltag 12, einen
Cosine-Fade an Spieltag 13–17 und ausschließlich Fresh ab Spieltag 18.

| Datensatz | Default V2 | Buchmacher | relativer Rückstand |
|---|---:|---:|---:|
| 11 Saisons, Confirm-Budget | **0,20559** | 0,19892 | 3,35 % |
| 2023/24–2025/26, High-Budget | **0,19797** | 0,19204 | ca. 3,1 % |

Im 11-Saison-Lauf verbessert der neue Default den alten identischen Übergang
von 0,21012 auf 0,20559. Der Gewinn beträgt 0,00453 RPS, tritt in neun von elf
Saisons auf und hat ein saison-geclustertes 95-%-Intervall von 0,00237 bis
0,00677.

Harte Wechsel und Fades mit Endpunkten zwischen Spieltag 12 und 22 liegen sehr
eng zusammen. Der Default ST12–18 ist ein verständlicher Kompromiss aus dem
breiten 11-Saison-Lauf und dem High-Budget-Test der drei jüngsten Saisons; der
exakte einzelne Spieltag wird nicht als bewiesen interpretiert.

Zusätzliche Cosine-Fades des globalen Ligalevel-Priors bis Saisonspiel 90, 135
oder 180 verbesserten die Rolling-Origin-Leistung nicht belastbar. Deshalb
bleibt der einfachere 144er-Prior ohne zweiten Fade-Hyperparameter Standard.

Stand: 28. Juli 2026.

## Korrigierte aktuelle Empfehlung: Real-xG und vollständiges V2

Die zuerst dokumentierten Saisonübergangsläufe nutzten trotz kontinuierlicher
Gamma-Likelihood nur das football-data-Schuss-Proxy-xG. Außerdem wurde im
damaligen Spätvergleich eine kurze Einzelketten-Replik als
`standalone_original` bezeichnet. Das war nicht das vollständige V2-Modell und
die daraus abgeleitete H17-Dauerempfehlung ist verworfen.

Der korrigierte Lauf verwendet für alle 3.060 Spiele aus 2016/17–2025/26 echtes
Understat-xG (100 % Abdeckung), das kontinuierliche Gamma-Modell (`phi=5`), den
Marktwertprior, feste leckfreie Paper-Hyperparameter und Walk-forward-Updates.
Für den späten Vergleich werden direkt die gespeicherten Wahrscheinlichkeiten
des großen Vierketten-V2-Laufs verwendet.

### Vor dem evaluierten V2-Start

| Modell, bis ungefähr Spieltag 24 | Spiele | RPS |
|---|---:|---:|
| Buchmacher | 2.135 | **0,19804** |
| **Soft-Blend h=10** | 2.135 | **0,20607** |
| Soft-Blend h=17 | 2.135 | 0,20619 |
| Cosine-Taper K30 | 2.135 | 0,20662 |
| Saisonstart-Modell ohne Blend | 2.135 | 0,20815 |
| Nur aktuelle Saison | 2.135 | 0,21179 |

H10 und H17 sind statistisch nicht unterscheidbar. H10 wird als einfacherer,
schneller ausblendender Default gewählt; das ist keine Behauptung eines
nachgewiesenen H10-Vorsprungs.

### Ab dem tatsächlichen V2-Prognosestart

| Modell | Spiele | RPS |
|---|---:|---:|
| Buchmacher | 925 | **0,19942** |
| **Vollständiges V2** | 925 | **0,20298** |
| Soft-Blend h=17 | 925 | 0,20617 |
| Soft-Blend h=10 | 925 | 0,20654 |
| Cosine-Taper K30 | 925 | 0,20706 |

V2 schlägt H17 um 0,00319 RPS. Das normale gepaarte 95%-Bootstrap-Intervall
beträgt 0,00039 bis 0,00601; das strengere saison-geclusterte Intervall beträgt
0,00141 bis 0,00502. V2 gewinnt in neun von zehn Einzelsaisons.

### Produktionspolicy über die ganze Saison

| Policy | RPS |
|---|---:|
| Buchmacher | **0,19846** |
| **H10 bis V2-Start, danach vollständiges V2** | **0,20514** |
| H17 bis V2-Start, danach vollständiges V2 | 0,20522 |
| K30 bis V2-Start, danach vollständiges V2 | 0,20552 |

Damit lautet der aktuelle Default: Saisonstart-Prior plus H10-Übergang in der
frühen Saison; ab dem ersten ehrlich evaluierten V2-Forecast ungefähr an
Spieltag 24 direkt das vollständige V2 verwenden. Ein früherer Wechsel wurde
hier nicht bewertet und wird daher nicht behauptet.

## Frühere Proxy-xG-Experimente (historischer Zwischenstand)

### Versuchsaufbau

Die Modellauswahl wurde zeitlich getrennt:

- Screening/Tuning: 2018/19–2021/22, 1.224 Spiele, kleines MCMC-Budget.
- Unangetastete Bestätigung: 2022/23–2024/25, 918 Spiele, deutlich größeres
  MCMC-Budget (`5000/3000/1500` Iterationen für Prior/Base/Warm-Refits).
- Beobachtung: kontinuierliches Proxy-xG aus den football-data-Schussdaten.
- Bewertung: Ranked Probability Score, niedriger ist besser.
- Alle Marktwerte stammen aus dem Snapshot vor dem jeweiligen Saisonstart.

Getestet wurden Carry-Gewichte 0,50 und 0,75, absolute Marktwerte,
Marktwertänderungen, doppelte frühe Prozessvarianz, ein reines Saisonmodell,
ein harter Reset nach 153 Spielen und Soft-Blends mit Halbwertszeiten 3, 6, 10
und 17 Spieltage. Anschließend wurden Cosine-Taper getestet, die den
Carry-Anteil weich bis Spieltag 18, 25 oder 30 exakt auf null bringen.

### Bestätigungsergebnis

| Variante | RPS |
|---|---:|
| Buchmacher-Schlusslinie | **0,19693** |
| **Marktwert-Prior + Cosine-Taper auf null bis ST 30** | **0,20848** |
| Marktwert-Prior + harter Midseason-Reset | 0,20856 |
| Marktwert-Prior + Cosine-Taper auf null bis ST 25 | 0,20873 |
| Marktwert-Prior + Soft-Blend, h=10 | 0,20881 |
| Marktwert-Prior + Soft-Blend, h=17 | 0,20888 |
| Marktwert-Prior + Cosine-Taper auf null bis ST 18 | 0,20932 |
| Carry-Prior ohne Marktwert + Soft-Blend, h=10 | 0,21041 |
| Marktwert-Prior, kein Ausblenden | 0,21190 |
| Marktwertänderung + schnelle frühe Dynamik | 0,21316 |
| Carry-Prior, kein Ausblenden | 0,21376 |
| Nur aktuelle Saison | 0,21455 |
| Feste Preseason-Stärken | 0,21647 |

Der empfohlene Marktwert-Soft-Blend verbessert gegenüber:

- demselben Marktwert-Prior ohne Ausblenden um 0,00310 RPS
  (95%-Bootstrap-CI 0,00015 bis 0,00602),
- dem Soft-Blend ohne Marktwert um 0,00160
  (CI 0,00032 bis 0,00288),
- dem ursprünglichen Carry-Filter ohne Marktwert um 0,00495
  (CI 0,00164 bis 0,00821).

Der Marktwertgewinn trat in allen drei Testsaisons auf. Er war erwartungsgemäß
am größten an Spieltag 1–5 (0,00713 RPS) und in Spielen mit mindestens einem
Aufsteiger (0,00310 RPS).

Der Cosine-Taper bis Spieltag 30 ist gepoolt 0,00008 besser als der harte Reset
und 0,00033 besser als Soft-Blend h=10. Beide Intervalle enthalten null; die
Varianten sind statistisch nicht unterscheidbar. Der Taper wird bevorzugt,
weil er ohne Prognosesprung auskommt und den Vorsaisoneinfluss dennoch
garantiert vollständig beendet.

### Frühere Proxy-xG-Empfehlung (verworfen)

Die folgende damalige Proxy-xG-Empfehlung ersetzte den früheren K30-Default,
wird aber durch die korrigierte Real-xG/V2-Policy oben nicht mehr verwendet.
Ein erweiterter Proxy-Lauf
über 2015/16–2025/26 mit unveränderten Kandidaten und Confirm-MCMC-Budget umfasst
3.366 Spiele. 2025/26 wurde dabei als neuer Schluss-Holdout separat betrachtet.

| Variante | RPS, 11 Saisons | RPS, 2025/26 |
|---|---:|---:|
| Buchmacher | **0,19892** | **0,18987** |
| **Marktwert-Prior + Soft-Blend h=17** | **0,20948** | **0,20440** |
| Marktwert-Prior + Soft-Blend h=10 | 0,20954 | 0,20472 |
| Marktwert-Prior + Cosine-Taper K30 | 0,21011 | 0,20525 |
| Marktwert-Prior ohne Ausblenden | 0,21130 | 0,20491 |
| Nur aktuelle Saison | 0,21359 | 0,20948 |

H17 verbessert K30 gepoolt um 0,00063 RPS. Das saison-geclusterte
95%-Bootstrap-Intervall beträgt 0,00004 bis 0,00125. H17 und H10 sind dagegen
praktisch gleichwertig: Differenz 0,00006, Intervall −0,00043 bis 0,00053.
Gegenüber `current_only` beträgt der H17-Vorteil 0,00410
(0,00209 bis 0,00606).

Innerhalb dieses Proxy-Laufs war H17 der Mittelwert-Sieger. K30 blieb eine
vertretbare
Policy-Alternative, falls der Vorsaisoneinfluss zwingend ab einem bestimmten
Spieltag exakt null sein soll; die Backtestzahlen sprechen aber nicht mehr
dafür, diese harte Bedingung zum Standard zu machen.

Zwei Filter parallel führen:

1. `carry_market`: Vorsaison-Endstärke mit Carry-Gewicht 0,75 plus
   `0.10 * z(log Preseason-Kaderwert)`.
2. `current_only`: Teamstärken nur aus Spielen der aktuellen Saison.

Die Ergebniswahrscheinlichkeiten werden mit einem exponentiellen Übergang
gemischt:

```text
w(k) = 0.5 ** ((k - 1) / 17)
p(k) = w(k) * p_carry_market + (1 - w(k)) * p_current_only
```

Damit beträgt das Carry-Gewicht ungefähr:

| Spieltag | Gewicht |
|---:|---:|
| 1 | 100 % |
| 5 | 84,9 % |
| 10 | 69,3 % |
| 15 | 56,5 % |
| 18 | 50,0 % |
| 24 | 39,2 % |
| 25 | 37,6 % |
| 30 | 30,7 % |
| 34 | 26,0 % |

Die frühe Prozessvarianz bleibt vorerst beim Faktor 1. Marktwertänderungen
werden nicht zusätzlich verwendet. Beide Erweiterungen waren im Screening
nicht robust besser als der einfachere absolute Marktwert-Prior.

### Alter Proxy-Spätvergleich (kein vollständiges V2)

Der erweiterte Vergleich umfasst jetzt 1.022 gemeinsame Spiele aus elf
Saisons. Das bisherige Standalone-Modell wird in jeder Saison ausschließlich
ab seinem tatsächlichen Prognosestart um Spieltag 24 bewertet.

| Modell | RPS | Log-Loss | Brier |
|---|---:|---:|---:|
| Buchmacher | **0,19962** | **0,98193** | **0,58482** |
| **Soft-Blend h=17** | **0,20962** | **1,01292** | **0,60593** |
| Soft-Blend h=10 | 0,21000 | 1,01414 | 0,60705 |
| Taper bis ST 30 | 0,21048 | 1,01570 | 0,60831 |
| Bisheriger Standalone-Walk-forward | 0,21098 | 1,01638 | 0,60933 |

H17 liegt 0,00136 RPS vor dem Standalone-Modell. Das saison-geclusterte
95%-Intervall von −0,00284 bis 0,00521 enthält deutlich null: Für die späte
Saisonphase ist kein belastbarer Qualitätsunterschied nachgewiesen. Im neuen
Holdout 2025/26 war das Standalone-Modell auf seinen 94 späten Spielen sogar
minimal besser als H17 (0,21636 gegenüber 0,21674), ebenfalls ohne belastbaren
Unterschied.

### Früherer Drei-Saisons-Vergleich

Der ursprüngliche Walk-forward beginnt in den drei Bestätigungssaisons bei
Saisonspiel 214/215, also ungefähr an Spieltag 24. Auf dem gemeinsamen Fenster
von 277 Spielen ergeben sich:

| Modell | RPS | Log-Loss | Brier |
|---|---:|---:|---:|
| Buchmacher | **0,20335** | **1,01106** | **0,60525** |
| Current-only / Taper bis ST 25 | **0,20870** | **1,02598** | **0,61577** |
| Taper bis ST 30 | 0,20872 | 1,02624 | 0,61591 |
| Exponentieller Soft-Blend h=10 | 0,20939 | 1,02835 | 0,61719 |
| Bisheriger Standalone-Walk-forward | 0,21315 | 1,03964 | 0,62582 |
| Carry-Filter ohne Ausblenden | 0,21927 | 1,06095 | 0,63776 |

Current-only/Taper verbessert den Standalone-Walk-forward um 0,00445 RPS; das
95%-Bootstrap-Intervall von −0,00224 bis 0,01114 enthält bei nur 277 Spielen
noch null. Saisonweise gewinnt Current-only in zwei von drei Saisons.

Die Modelle sind nicht identisch: Der bisherige Standalone-Backtest verwendet
weiter einen Marktwert-Teamprior und schätzt das globale Torniveau aus dem
aktuellen Saisonpräfix. `current_only` verwendet keinen Teamprior mehr und hält
das globale Torniveau auf der historischen, vor Saisonstart bekannten Basis.
Der Vergleich misst daher die komplette Forecast-Policy, nicht nur einen
isolierten Carry-Effekt.

## Verbleibende Grenzen

- H10 und H17 sind im frühen Real-xG-Fenster statistisch nicht unterscheidbar.
- Die Übergangskandidaten liefen mit schnellem Einzelketten-Confirm-Budget;
  das vollständige V2 stammt dagegen aus dem großen Vierkettenlauf. Enge
  H10/H17-Unterschiede dürfen deshalb nicht überinterpretiert werden.
- Ein Wechsel vor dem bisherigen V2-Holdout um Spieltag 24 ist noch nicht
  evaluiert.
- Der Buchmacher bleibt auch gegenüber der kombinierten Policy besser.

## Reproduzieren

```powershell
uv run python v2/preseason_experiments.py --stage screen --output-root v2/output
uv run python v2/preseason_experiments.py --stage confirm `
  --configs carry75 level_all10 delta05_early2 --output-root v2/output
uv run python v2/preseason_experiments.py --stage confirm `
  --xg-source real --configs level_all10 --bundle-configs level_all10 `
  --output-root v2/output
uv run python v2/preseason_v2_late_comparison.py `
  --experiment-dir v2/output/preseason_experiment_confirm_<timestamp> `
  --v2-run-dir v2/output/multiseason_<timestamp> `
  --output-root v2/output
uv run python v2/preseason_late_comparison.py `
  --experiment-dir v2/output/preseason_experiment_confirm_<timestamp> `
  --output-root v2/output
uv run python v2/preseason_extended_analysis.py `
  --experiment-dir v2/output/preseason_experiment_confirm_<timestamp> `
  --late-dir v2/output/preseason_late_comparison_<timestamp> `
  --output-root v2/output
```
