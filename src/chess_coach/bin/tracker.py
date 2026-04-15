"""Persistance SQLite des snapshots hebdomadaires et suivi de progression."""

import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import date
from pathlib import Path

from chess_coach.bin.coach import TrainingPlan
from chess_coach.bin.pattern_detector import WeaknessProfile

_CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_snapshots (
    week        TEXT PRIMARY KEY,
    elo         INTEGER NOT NULL,
    acpl        REAL NOT NULL,
    profile     TEXT NOT NULL,
    plan        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS puzzle_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    theme       TEXT NOT NULL,
    solved      INTEGER NOT NULL,
    attempted   INTEGER NOT NULL,
    accuracy    REAL NOT NULL
);
"""


def init_db(db_path: str | Path = "chess_coach.db") -> sqlite3.Connection:
    """Initialise la base SQLite et retourne la connexion.

    Crée le fichier et les tables s'ils n'existent pas.

    Args:
        db_path: Chemin vers le fichier SQLite.

    Returns:
        Connexion SQLite ouverte.

    Examples:
        >>> conn = init_db(":memory:")
        >>> conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        [('weekly_snapshots',), ('puzzle_sessions',)]
        >>> conn.close()
    """
    path = Path(db_path)
    if str(db_path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(_CREATE_SCHEMA)
    conn.commit()
    logging.info("init_db : base initialisée à %s", db_path)
    return conn


def save_snapshot(
    conn: sqlite3.Connection,
    elo: int,
    profile: WeaknessProfile,
    plan: TrainingPlan,
) -> None:
    """Sauvegarde le snapshot hebdomadaire dans la base.

    Utilise la date courante comme clé (``YYYY-MM-DD``).
    Si un snapshot existe déjà pour cette semaine, il est écrasé.

    Args:
        conn: Connexion SQLite ouverte.
        elo: Elo courant du joueur.
        profile: Profil de faiblesses de la semaine.
        plan: Plan d'entraînement généré par Claude.

    Examples:
        >>> from chess_coach.bin.pattern_detector import WeaknessProfile
        >>> from chess_coach.bin.coach import TrainingPlan
        >>> conn = init_db(":memory:")
        >>> p: WeaknessProfile = {
        ...     "total_games": 5, "avg_acpl": 40.0, "weakest_phase": "middlegame",
        ...     "phase_breakdown": {}, "problematic_openings": [],
        ...     "avg_cp_loss_by_phase": {}, "worst_positions": [],
        ... }
        >>> t: TrainingPlan = {
        ...     "week_theme": "test", "daily_tasks": [],
        ...     "key_concepts": [], "success_metrics": "",
        ... }
        >>> save_snapshot(conn, 1500, p, t)
        >>> conn.execute("SELECT elo FROM weekly_snapshots").fetchone()
        (1500,)
        >>> conn.close()
    """
    profile_serializable = dict(profile)
    profile_serializable["worst_positions"] = [
        asdict(err) for err in profile["worst_positions"]
    ]

    conn.execute(
        """
        INSERT OR REPLACE INTO weekly_snapshots
        (week, elo, acpl, profile, plan, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(date.today()),
            elo,
            profile["avg_acpl"],
            json.dumps(profile_serializable, ensure_ascii=False),
            json.dumps(plan, ensure_ascii=False),
            date.today().isoformat(),
        ),
    )
    conn.commit()
    logging.info(
        "save_snapshot : snapshot sauvegardé (Elo %d, ACPL %.1f)",
        elo,
        profile["avg_acpl"],
    )


def get_progress_trend(
    conn: sqlite3.Connection,
    weeks: int = 8,
) -> list[dict[str, object]]:
    """Retourne l'évolution de l'ACPL sur les N dernières semaines.

    Args:
        conn: Connexion SQLite ouverte.
        weeks: Nombre de semaines à récupérer (défaut : 8).

    Returns:
        Liste de dicts ``{"week", "elo", "acpl"}`` du plus récent au plus ancien.

    Examples:
        >>> conn = init_db(":memory:")
        >>> get_progress_trend(conn, weeks=4)
        []
        >>> conn.close()
    """
    rows = conn.execute(
        """
        SELECT week, elo, acpl
        FROM weekly_snapshots
        ORDER BY week DESC
        LIMIT ?
        """,
        (weeks,),
    ).fetchall()
    return [{"week": r[0], "elo": r[1], "acpl": r[2]} for r in rows]
