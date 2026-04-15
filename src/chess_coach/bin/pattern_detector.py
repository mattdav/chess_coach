"""Agrégation des GameReports en profil de faiblesses structuré."""

import logging
from collections import Counter
from typing import TypedDict

from chess_coach.bin.analyzer import GameReport, MoveError


class WeaknessProfile(TypedDict):
    """Profil de faiblesses agrégé sur un ensemble de parties.

    Examples:
        >>> p: WeaknessProfile = {
        ...     "total_games": 10,
        ...     "avg_acpl": 45.2,
        ...     "weakest_phase": "middlegame",
        ...     "phase_breakdown": {"opening": 3, "middlegame": 8, "endgame": 2},
        ...     "category_breakdown": {"blunder": 2, "mistake": 5, "dubious": 4},
        ...     "problematic_openings": [("B30", "Sicilian Defense", 4)],
        ...     "avg_cp_loss_by_phase": {
        ...         "opening": 75.0, "middlegame": 180.0, "endgame": 75.0
        ...     },
        ...     "worst_positions": [],
        ...     "annotated_pgns": [],
        ... }
        >>> p["weakest_phase"]
        'middlegame'
    """

    total_games: int
    avg_acpl: float
    weakest_phase: str
    phase_breakdown: dict[str, int]
    category_breakdown: dict[str, int]  # blunder / mistake / dubious
    # Tuples (code_ECO, nom_ouverture, nb_erreurs), triés par nb_erreurs desc.
    # Le code ECO est toujours présent (source : header [ECO] de caissAI).
    # Le nom est le header [Opening] si disponible, sinon le code ECO.
    problematic_openings: list[tuple[str, str, int]]
    avg_cp_loss_by_phase: dict[str, float]
    worst_positions: list[MoveError]  # 10 pires erreurs toutes parties
    annotated_pgns: list[str]  # PGN annotés bruts (un par partie)


def build_weakness_profile(reports: list[GameReport]) -> WeaknessProfile:
    """Agrège les rapports de parties en un profil de faiblesses.

    Les ouvertures problématiques sont agrégées par **code ECO** (toujours
    présent dans les annotations caissAI) et non par nom d'ouverture
    (absent dans les anciennes annotations).

    Args:
        reports: Rapports issus de ``analyzer.report_from_pgn``.

    Returns:
        Profil structuré prêt à être consommé par ``coach.generate_weekly_plan``.

    Examples:
        >>> from chess_coach.bin.analyzer import GameReport
        >>> profile = build_weakness_profile([])
        >>> profile["total_games"]
        0
        >>> profile["weakest_phase"]
        'middlegame'
    """
    if not reports:
        return WeaknessProfile(
            total_games=0,
            avg_acpl=0.0,
            weakest_phase="middlegame",
            phase_breakdown={},
            category_breakdown={},
            problematic_openings=[],
            avg_cp_loss_by_phase={
                "opening": 0.0,
                "middlegame": 0.0,
                "endgame": 0.0,
            },
            worst_positions=[],
            annotated_pgns=[],
        )

    phase_errors: Counter[str] = Counter()
    category_errors: Counter[str] = Counter()
    # Agrégation par code ECO : {eco: nb_erreurs}
    eco_errors: Counter[str] = Counter()
    # Nom associé à chaque ECO (dernier vu, ou le code lui-même si absent)
    eco_names: dict[str, str] = {}
    cp_loss_by_phase: dict[str, list[int]] = {
        "opening": [],
        "middlegame": [],
        "endgame": [],
    }
    all_errors: list[MoveError] = []
    annotated_pgns: list[str] = []

    for report in reports:
        if report.annotated_pgn:
            annotated_pgns.append(report.annotated_pgn)

        eco = report.eco.strip()
        if eco:
            eco_errors[eco] += len(report.errors)
            # Préférer le nom d'ouverture au code brut quand disponible
            name = (
                report.opening
                if report.opening and report.opening != "Unknown"
                else eco
            )
            eco_names[eco] = name

        for err in report.errors:
            phase_errors[err.phase] += 1
            category_errors[err.category] += 1
            cp_loss_by_phase[err.phase].append(err.cp_loss)
            all_errors.append(err)

    weakest_phase = phase_errors.most_common(1)[0][0] if phase_errors else "middlegame"
    avg_acpl = sum(r.acpl for r in reports) / len(reports)
    worst_positions = sorted(all_errors, key=lambda e: e.cp_loss, reverse=True)[:10]

    # Construire la liste (eco, nom, nb_erreurs) triée par nb_erreurs desc
    problematic_openings: list[tuple[str, str, int]] = [
        (eco, eco_names.get(eco, eco), count)
        for eco, count in eco_errors.most_common(5)
    ]

    profile = WeaknessProfile(
        total_games=len(reports),
        avg_acpl=round(avg_acpl, 1),
        weakest_phase=weakest_phase,
        phase_breakdown=dict(phase_errors),
        category_breakdown=dict(category_errors),
        problematic_openings=problematic_openings,
        avg_cp_loss_by_phase={
            phase: round(sum(losses) / len(losses), 1) if losses else 0.0
            for phase, losses in cp_loss_by_phase.items()
        },
        worst_positions=worst_positions,
        annotated_pgns=annotated_pgns,
    )

    logging.info(
        "build_weakness_profile : %d parties — ACPL %.1f — phase faible : %s "
        "— blunders %d / mistakes %d / dubious %d",
        profile["total_games"],
        profile["avg_acpl"],
        profile["weakest_phase"],
        category_errors.get("blunder", 0),
        category_errors.get("mistake", 0),
        category_errors.get("dubious", 0),
    )
    return profile
