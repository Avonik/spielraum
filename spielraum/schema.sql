PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    code TEXT NOT NULL,
    primary_color TEXT NOT NULL,
    secondary_color TEXT NOT NULL,
    badge_variant TEXT NOT NULL CHECK (badge_variant IN ('circle','diamond','oval','shield'))
);

CREATE TABLE IF NOT EXISTS fixtures (
    id TEXT PRIMARY KEY,
    season TEXT NOT NULL,
    matchday INTEGER NOT NULL CHECK (matchday BETWEEN 1 AND 34),
    kickoff_utc TEXT NOT NULL,
    home_team_id INTEGER NOT NULL REFERENCES teams(id),
    away_team_id INTEGER NOT NULL REFERENCES teams(id),
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','live','finished','postponed')),
    UNIQUE (season, matchday, home_team_id, away_team_id)
);

CREATE TABLE IF NOT EXISTS model_versions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    git_sha TEXT,
    config_json TEXT NOT NULL,
    artifact_sha256 TEXT
);

CREATE TABLE IF NOT EXISTS published_snapshots (
    id TEXT PRIMARY KEY,
    model_version_id TEXT NOT NULL REFERENCES model_versions(id),
    season TEXT NOT NULL,
    matchday INTEGER NOT NULL,
    published_at TEXT NOT NULL,
    manifest_path TEXT,
    manifest_sha256 TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('preview','live'))
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id TEXT NOT NULL REFERENCES fixtures(id),
    snapshot_id TEXT NOT NULL REFERENCES published_snapshots(id),
    model_version_id TEXT NOT NULL REFERENCES model_versions(id),
    published_at TEXT NOT NULL,
    p_home REAL NOT NULL CHECK (p_home BETWEEN 0 AND 1),
    p_draw REAL NOT NULL CHECK (p_draw BETWEEN 0 AND 1),
    p_away REAL NOT NULL CHECK (p_away BETWEEN 0 AND 1),
    CHECK (abs(p_home + p_draw + p_away - 1.0) < 0.00001),
    UNIQUE (fixture_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS results (
    fixture_id TEXT PRIMARY KEY REFERENCES fixtures(id),
    home_goals INTEGER NOT NULL CHECK (home_goals >= 0),
    away_goals INTEGER NOT NULL CHECK (away_goals >= 0),
    status TEXT NOT NULL CHECK (status IN ('provisional','finished')),
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_strengths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL REFERENCES published_snapshots(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    season TEXT NOT NULL,
    matchday INTEGER NOT NULL,
    attack_index REAL NOT NULL,
    defense_index REAL NOT NULL,
    UNIQUE (snapshot_id, team_id, matchday)
);

CREATE TABLE IF NOT EXISTS placement_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL REFERENCES published_snapshots(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    median_rank REAL NOT NULL,
    low_rank INTEGER NOT NULL,
    high_rank INTEGER NOT NULL,
    p_title REAL NOT NULL,
    p_top4 REAL NOT NULL,
    p_relegation REAL NOT NULL,
    simulations INTEGER NOT NULL,
    UNIQUE (snapshot_id, team_id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running','success','deferred','failed','skipped')),
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS scheduler_state (
    job TEXT PRIMARY KEY,
    last_attempt_at TEXT NOT NULL,
    last_success_at TEXT,
    last_status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fixtures_round ON fixtures(season, matchday, kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_predictions_fixture_time ON predictions(fixture_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_strengths_season_team ON team_strengths(season, team_id, matchday);

CREATE TRIGGER IF NOT EXISTS predictions_no_update
BEFORE UPDATE ON predictions BEGIN
    SELECT RAISE(ABORT, 'published predictions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS predictions_no_delete
BEFORE DELETE ON predictions BEGIN
    SELECT RAISE(ABORT, 'published predictions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS predictions_before_kickoff
BEFORE INSERT ON predictions
WHEN datetime(NEW.published_at) >= datetime((SELECT kickoff_utc FROM fixtures WHERE id = NEW.fixture_id))
BEGIN
    SELECT RAISE(ABORT, 'predictions must be published before kickoff');
END;

CREATE TRIGGER IF NOT EXISTS fixture_kickoff_no_update
BEFORE UPDATE OF kickoff_utc, home_team_id, away_team_id ON fixtures
WHEN EXISTS (SELECT 1 FROM predictions WHERE fixture_id = OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'published fixture identity is immutable');
END;

CREATE TRIGGER IF NOT EXISTS snapshots_no_update
BEFORE UPDATE ON published_snapshots BEGIN
    SELECT RAISE(ABORT, 'published snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS snapshots_no_delete
BEFORE DELETE ON published_snapshots BEGIN
    SELECT RAISE(ABORT, 'published snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS strengths_no_update
BEFORE UPDATE ON team_strengths BEGIN
    SELECT RAISE(ABORT, 'published team strengths are immutable');
END;

CREATE TRIGGER IF NOT EXISTS strengths_no_delete
BEFORE DELETE ON team_strengths BEGIN
    SELECT RAISE(ABORT, 'published team strengths are immutable');
END;

CREATE TRIGGER IF NOT EXISTS placements_no_update
BEFORE UPDATE ON placement_forecasts BEGIN
    SELECT RAISE(ABORT, 'published placement forecasts are immutable');
END;

CREATE TRIGGER IF NOT EXISTS placements_no_delete
BEFORE DELETE ON placement_forecasts BEGIN
    SELECT RAISE(ABORT, 'published placement forecasts are immutable');
END;

CREATE TRIGGER IF NOT EXISTS finished_results_no_update
BEFORE UPDATE ON results WHEN OLD.status = 'finished' BEGIN
    SELECT RAISE(ABORT, 'finished results are immutable');
END;

CREATE TRIGGER IF NOT EXISTS finished_results_no_delete
BEFORE DELETE ON results WHEN OLD.status = 'finished' BEGIN
    SELECT RAISE(ABORT, 'finished results are immutable');
END;
