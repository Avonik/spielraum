# Spielraum Forecast Lab

Pi-first Portfolio-Webseite für das Bundesliga-V2-Modell. Der aktuelle Stand umfasst responsives Frontend, read-only API, SQLite-Persistenz, unveränderliche Forecasts, atomare Snapshot-Veröffentlichung, Live-Datenadapter, Zeitplan und ARM64-Container. Bis zum ersten produktiven Modelllauf zeigt die Seite weiterhin klar markierte Preview-Daten.

## Architektur

- `web/`: Vinext/React-Frontend; lädt `/api/dashboard` und fällt ohne API auf markierte Preview-Daten zurück.
- `spielraum/`: FastAPI, SQLite-Schema, Publishing- und Scheduling-Layer.
- `runtime/`: persistente SQLite-Datei und architekturunabhängige JSON/NPZ-Artefakte; wird nicht committed.
- `scheduler`: OpenLigaDB-Spielplan und Ergebnisse während der Spielzeiten alle 30 Minuten; V2-Modell montags 03:30 Uhr in `Europe/Berlin`.
- `Caddy`: ein öffentlicher Entry-Point, später automatisch mit HTTPS bei einem echten Domainnamen.

SQLite läuft im WAL-Modus mit genau einem schreibenden Scheduler. `predictions`, veröffentlichte Snapshots, Teamstärken und Platzierungsprognosen sind per Datenbank-Trigger append-only. Nach Anpfiff kann für ein Spiel keine neue Prognose gespeichert werden. Ergebnisse werden separat ergänzt und sind nach Status `finished` ebenfalls gesperrt.

## Lokal starten

```powershell
$env:SPIELRAUM_DATA_DIR="runtime"
.\.venv\Scripts\python.exe -m spielraum.cli init --seed-preview
.\.venv\Scripts\uvicorn.exe spielraum.api:app --reload --port 8000
```

In einem zweiten Terminal:

```powershell
cd web
npm run dev
```

Alternativ baut `docker compose up --build` denselben Stack wie auf dem Pi.

## Produktions-Snapshot

Ein Modelllauf schreibt JSON mit:

- `snapshot_id`, `season`, `matchday`, `published_at`, `mode`
- `model`: eindeutige ID, Zeitstempel, Git-SHA und vollständige Konfiguration
- Club-Metadaten für die eigenständigen geometrischen CSS-Badges
- Fixtures mit UTC-Anpfiff und `[p_home, p_draw, p_away]`
- optionale aktuelle Angriffs-/Abwehrstärken und Platzierungssimulationen

Veröffentlichen:

```powershell
python -m spielraum.cli publish path\to\snapshot.json
```

Die Datei wird validiert, atomar nach `runtime/artifacts/<snapshot_id>/snapshot.json` geschrieben, SHA-256-gehasht und in einer einzigen SQLite-Transaktion veröffentlicht. Scheitert ein Schritt, sieht die Webseite weiter den letzten intakten Snapshot.

Der über `SPIELRAUM_MODEL_COMMAND` konfigurierte Adapter muss in seiner letzten stdout-Zeile liefern:

```json
{"matchday_complete": true, "xg_complete": true, "snapshot_path": "/data/inbox/snapshot.json"}
```

Bei unvollständigem Spieltag oder fehlendem xG wird der Lauf zurückgestellt. Der Ergebnis-Adapter liefert den kompletten Spielplan plus abgeschlossene Ergebnisse. Dadurch funktioniert auch ein erster Start mitten in der Saison:

```json
{"source":"OpenLigaDB (ODbL)", "teams":["..."], "fixtures":["..."], "results":[{"fixture_id":"2627-01-fcb-vfb", "home_goals":2, "away_goals":1, "status":"finished", "observed_at":"2026-08-28T21:00:00+02:00"}]}
```

Die Live-Pipeline verwendet [OpenLigaDB](https://openligadb.de/) für Ansetzungen und Resultate sowie Understat über `soccerdata` für Match-xG. Fehlt nach einem Spiel noch echtes xG oder ist der Marktwertstichtag noch nicht erreicht, veröffentlicht der Scheduler keine halbfertige Prognose, sondern versucht den Lauf im Zwei-Stunden-Takt erneut. Das Frontend fragt den aktuellen Dashboard-Snapshot alle fünf Minuten und beim Zurückkehren in den Browser-Tab neu ab.

## Marktwerte 2026/27

`v2.market_value.fetch_current_season_only()` ist der einzige reguläre neue Abruf und hart auf `season_id=2026` begrenzt. Bis 15.08.2026 verwendet die Pipeline bewusst den gespeicherten vorläufigen Stichtag, aktuell 29.07.2026. Am offiziellen Stichtag wird dieser Stand automatisch einmal ersetzt. Die bereits gecachten historischen Saisons werden weder angefragt noch überschrieben. Der Worker kopiert den historischen Ausgangs-Cache einmal nach `runtime/cache/market-values.csv`; nur diese persistente Kopie wird um 2026/27 ergänzt.

## Auf den Raspberry Pi 5 übertragen

Auf dem Pi einmal Raspberry Pi OS 64-bit und Docker installieren. Dann vom Desktop:

```powershell
.\scripts\deploy-pi.ps1 -PiHost spielraum.local
```

Der Source-Transfer schließt lokale Caches, Outputs und `runtime/` bewusst aus; die persistente Pi-Datenbank bleibt bei Deployments erhalten. Für eine einmalige Übernahme eines Modellzustands zuerst `python -m spielraum.cli export` ausführen und den entstandenen, gehashten Export separat in das Pi-`runtime/` übernehmen.

Die 8 GB des Raspberry Pi 5 reichen für API, Web, SQLite und den wöchentlichen MCMC-Worker. Der Worker läuft getrennt von der API. Numba-Cachedateien werden nicht zwischen Windows/x86 und Linux/ARM64 kopiert, sondern auf dem Pi neu erzeugt.
