from __future__ import annotations

import json
from pathlib import Path

from .storage import transaction


CLUBS = {
    "bayern": ("Bayern München", "Bayern", "FCB", "#d51d32", "#f4efe6", "circle"),
    "stuttgart": ("VfB Stuttgart", "Stuttgart", "VFB", "#f1eee7", "#d71832", "shield"),
    "elversberg": ("SV Elversberg", "Elversberg", "ELV", "#f1d32f", "#151515", "circle"),
    "leverkusen": ("Bayer Leverkusen", "Leverkusen", "B04", "#e52332", "#101010", "shield"),
    "koeln": ("1. FC Köln", "Köln", "KOE", "#f4f0e8", "#d31f32", "circle"),
    "hoffenheim": ("TSG Hoffenheim", "Hoffenheim", "TSG", "#1b64b0", "#f0eee7", "shield"),
    "union": ("Union Berlin", "Union Berlin", "FCU", "#d51d32", "#f5d537", "oval"),
    "frankfurt": ("Eintracht Frankfurt", "Frankfurt", "SGE", "#151515", "#e32936", "circle"),
    "mainz": ("Mainz 05", "Mainz", "M05", "#df1f37", "#f5f0e7", "circle"),
    "paderborn": ("SC Paderborn", "Paderborn", "SCP", "#1768a8", "#161616", "circle"),
    "leipzig": ("RB Leipzig", "Leipzig", "RBL", "#f1eee7", "#d51e38", "shield"),
    "gladbach": ("Borussia M'gladbach", "M'gladbach", "BMG", "#171717", "#f3efe6", "diamond"),
    "dortmund": ("Borussia Dortmund", "Dortmund", "BVB", "#f0d522", "#111111", "circle"),
    "hamburg": ("Hamburger SV", "Hamburg", "HSV", "#1767a6", "#f4f0e8", "diamond"),
    "freiburg": ("SC Freiburg", "Freiburg", "SCF", "#f3efe7", "#d92035", "oval"),
    "bremen": ("Werder Bremen", "Bremen", "SVW", "#14824b", "#f4f0e8", "diamond"),
    "augsburg": ("FC Augsburg", "Augsburg", "FCA", "#b62930", "#17754a", "shield"),
    "schalke": ("FC Schalke 04", "Schalke", "S04", "#1769ad", "#f3efe7", "circle"),
    "heidenheim": ("1. FC Heidenheim", "Heidenheim", "FCH", "#195ba3", "#e72d36", "circle"),
    "stpauli": ("FC St. Pauli", "St. Pauli", "STP", "#5b3524", "#f2eee6", "circle"),
    "wolfsburg": ("VfL Wolfsburg", "Wolfsburg", "WOB", "#65b32e", "#f2eee6", "circle"),
}

CURRENT_FIXTURES = [
    ("2627-01-fcb-vfb", "2026-08-28T18:30:00+00:00", "bayern", "stuttgart", (.57, .23, .20)),
    ("2627-01-elv-b04", "2026-08-29T13:30:00+00:00", "elversberg", "leverkusen", (.17, .23, .60)),
    ("2627-01-koe-tsg", "2026-08-29T13:30:00+00:00", "koeln", "hoffenheim", (.38, .28, .34)),
    ("2627-01-fcu-sge", "2026-08-29T13:30:00+00:00", "union", "frankfurt", (.32, .29, .39)),
    ("2627-01-m05-scp", "2026-08-29T13:30:00+00:00", "mainz", "paderborn", (.52, .27, .21)),
    ("2627-01-rbl-bmg", "2026-08-29T13:30:00+00:00", "leipzig", "gladbach", (.55, .24, .21)),
    ("2627-01-bvb-hsv", "2026-08-29T16:30:00+00:00", "dortmund", "hamburg", (.63, .22, .15)),
    ("2627-01-scf-svw", "2026-08-30T13:30:00+00:00", "freiburg", "bremen", (.46, .28, .26)),
    ("2627-01-fca-s04", "2026-08-30T15:30:00+00:00", "augsburg", "schalke", (.43, .29, .28)),
]

HISTORY = [
    ("2526-34-fch-m05", "2026-05-16T13:30:00+00:00", "heidenheim", "mainz", (.316, .212, .472), (0, 2)),
    ("2526-34-b04-hsv", "2026-05-16T13:30:00+00:00", "leverkusen", "hamburg", (.724, .151, .125), (1, 1)),
    ("2526-34-stp-wob", "2026-05-16T13:30:00+00:00", "stpauli", "wolfsburg", (.294, .277, .429), (1, 3)),
    ("2526-34-bmg-tsg", "2026-05-16T13:30:00+00:00", "gladbach", "hoffenheim", (.342, .256, .402), (4, 0)),
    ("2526-34-fcu-fca", "2026-05-16T13:30:00+00:00", "union", "augsburg", (.409, .252, .339), (4, 0)),
    ("2526-34-svw-bvb", "2026-05-16T13:30:00+00:00", "bremen", "dortmund", (.249, .255, .496), (0, 2)),
]


def seed_preview(database_path: str | Path) -> None:
    """Load clearly-labelled demo rows without replacing any existing data."""
    with transaction(database_path) as connection:
        connection.executemany(
            """INSERT OR IGNORE INTO teams
               (slug, display_name, short_name, code, primary_color, secondary_color, badge_variant)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(slug, *values) for slug, values in CLUBS.items()],
        )
        team_ids = {r["slug"]: r["id"] for r in connection.execute("SELECT id, slug FROM teams")}
        connection.executemany(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES (?, ?)",
            [("current_season", "2026/27"), ("current_matchday", "1"), ("data_mode", "preview")],
        )
        connection.execute(
            """INSERT OR IGNORE INTO model_versions
               (id, created_at, config_json, artifact_sha256) VALUES (?, ?, ?, ?)""",
            ("preview-2026-07-29", "2026-07-29T12:00:00+00:00", json.dumps({"preview": True}), None),
        )
        connection.execute(
            """INSERT OR IGNORE INTO model_versions
               (id, created_at, config_json, artifact_sha256) VALUES (?, ?, ?, ?)""",
            ("historic-2025-26", "2026-05-15T12:00:00+00:00", json.dumps({"source": "stored high-budget output"}), None),
        )
        connection.execute(
            """INSERT OR IGNORE INTO published_snapshots
               (id, model_version_id, season, matchday, published_at, mode)
               VALUES ('preview-md1', 'preview-2026-07-29', '2026/27', 1, '2026-07-29T12:00:00+00:00', 'preview')"""
        )
        connection.execute(
            """INSERT OR IGNORE INTO published_snapshots
               (id, model_version_id, season, matchday, published_at, mode)
               VALUES ('historic-md34', 'historic-2025-26', '2025/26', 34, '2026-05-15T12:00:00+00:00', 'live')"""
        )
        for fixture_id, kickoff, home, away, probs in CURRENT_FIXTURES:
            connection.execute(
                """INSERT OR IGNORE INTO fixtures
                   (id, season, matchday, kickoff_utc, home_team_id, away_team_id, status)
                   VALUES (?, '2026/27', 1, ?, ?, ?, 'scheduled')""",
                (fixture_id, kickoff, team_ids[home], team_ids[away]),
            )
            connection.execute(
                """INSERT OR IGNORE INTO predictions
                   (fixture_id, snapshot_id, model_version_id, published_at, p_home, p_draw, p_away)
                   VALUES (?, 'preview-md1', 'preview-2026-07-29', '2026-07-29T12:00:00+00:00', ?, ?, ?)""",
                (fixture_id, *probs),
            )
        for fixture_id, kickoff, home, away, probs, score in HISTORY:
            connection.execute(
                """INSERT OR IGNORE INTO fixtures
                   (id, season, matchday, kickoff_utc, home_team_id, away_team_id, status)
                   VALUES (?, '2025/26', 34, ?, ?, ?, 'finished')""",
                (fixture_id, kickoff, team_ids[home], team_ids[away]),
            )
            connection.execute(
                """INSERT OR IGNORE INTO predictions
                   (fixture_id, snapshot_id, model_version_id, published_at, p_home, p_draw, p_away)
                   VALUES (?, 'historic-md34', 'historic-2025-26', '2026-05-15T12:00:00+00:00', ?, ?, ?)""",
                (fixture_id, *probs),
            )
            connection.execute(
                """INSERT OR IGNORE INTO results
                   (fixture_id, home_goals, away_goals, status, observed_at, source)
                   VALUES (?, ?, ?, 'finished', '2026-05-16T18:00:00+00:00', 'stored result')""",
                (fixture_id, *score),
            )

        strength_series = {
            "bayern": ([76, 78, 81, 82, 84, 86, 89, 88], [65, 67, 68, 71, 73, 74, 76, 78]),
            "dortmund": ([68, 69, 72, 71, 74, 76, 75, 78], [58, 59, 61, 63, 62, 64, 66, 67]),
            "leverkusen": ([72, 73, 74, 77, 79, 78, 80, 82], [67, 68, 70, 69, 72, 74, 75, 76]),
            "frankfurt": ([61, 64, 63, 66, 68, 69, 71, 70], [60, 61, 63, 62, 64, 65, 67, 68]),
        }
        for slug, (attack, defense) in strength_series.items():
            for day, (a, d) in enumerate(zip(attack, defense), start=1):
                connection.execute(
                    """INSERT OR IGNORE INTO team_strengths
                       (snapshot_id, team_id, season, matchday, attack_index, defense_index)
                       VALUES ('preview-md1', ?, '2026/27', ?, ?, ?)""",
                    (team_ids[slug], day, a, d),
                )

        placements = [
            ("bayern", 1, 1, 4, .52, .83, .001), ("dortmund", 3, 1, 7, .15, .61, .006),
            ("leverkusen", 3, 1, 7, .14, .59, .007), ("leipzig", 4, 1, 9, .09, .47, .015),
            ("frankfurt", 6, 2, 11, .035, .29, .035), ("stuttgart", 7, 2, 12, .025, .23, .055),
            ("freiburg", 8, 3, 14, .012, .15, .09), ("hoffenheim", 9, 4, 15, .008, .11, .13),
            ("gladbach", 10, 4, 16, .006, .09, .17), ("bremen", 11, 5, 17, .004, .07, .22),
            ("union", 12, 6, 17, .003, .05, .28), ("mainz", 12, 6, 17, .003, .05, .29),
            ("augsburg", 13, 7, 18, .002, .035, .34), ("koeln", 14, 8, 18, .001, .025, .41),
            ("hamburg", 15, 8, 18, .001, .02, .47), ("schalke", 15, 8, 18, .001, .018, .49),
            ("paderborn", 16, 9, 18, 0, .01, .58), ("elversberg", 17, 10, 18, 0, .008, .65),
        ]
        for slug, median, low, high, title, top4, relegation in placements:
            connection.execute(
                """INSERT OR IGNORE INTO placement_forecasts
                   (snapshot_id, team_id, median_rank, low_rank, high_rank, p_title, p_top4, p_relegation, simulations)
                   VALUES ('preview-md1', ?, ?, ?, ?, ?, ?, ?, 50000)""",
                (team_ids[slug], median, low, high, title, top4, relegation),
            )
