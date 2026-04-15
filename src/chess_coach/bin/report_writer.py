"""Génération du livrable Markdown du plan d'entraînement."""

import logging
from datetime import date
from pathlib import Path

from chess_coach.bin.coach import TrainingPlan
from chess_coach.bin.gm_games import OpeningStudy
from chess_coach.bin.pattern_detector import WeaknessProfile

# Emojis par catégorie d'erreur
_CATEGORY_ICON = {"blunder": "🔴", "mistake": "🟠", "dubious": "🟡"}
_CATEGORY_LABEL = {"blunder": "Gaffe", "mistake": "Erreur", "dubious": "Douteux"}

# Emojis par type d'exercice
_EXERCISE_ICON = {
    "puzzles": "🧩",
    "game_analysis": "🔍",
    "opening_study": "📖",
    "endgame": "♟️",
}

# Emojis par phase de jeu
_PHASE_ICON = {"opening": "🌱", "middlegame": "⚔️", "endgame": "🏁"}

# Résultat humain
_RESULT_LABEL = {"white": "1-0", "black": "0-1", "draw": "½-½"}


def write_training_plan(
    profile: WeaknessProfile,
    plan: TrainingPlan,
    player_name: str,
    player_elo: int,
    output_dir: Path,
    gm_studies: list[OpeningStudy] | None = None,
) -> Path:
    """Génère le fichier Markdown du plan d'entraînement hebdomadaire.

    Args:
        profile: Profil de faiblesses de la session.
        plan: Plan d'entraînement généré par Claude.
        player_name: Nom du joueur.
        player_elo: Elo courant.
        output_dir: Dossier de sortie.
        gm_studies: Études de parties de GM.

    Returns:
        Chemin du fichier Markdown généré.

    Examples:
        >>> callable(write_training_plan)
        True
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    stem = today.strftime("%Y-%m-%d")
    out_path = output_dir / f"{stem}_plan.md"

    lines: list[str] = []
    _header(lines, plan, player_name, player_elo, today)
    _analysis_summary(lines, profile)
    _weekly_plan(lines, plan)
    _gm_studies(lines, gm_studies)
    _review(lines)

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logging.info("write_training_plan : plan écrit → %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _header(
    lines: list[str],
    plan: TrainingPlan,
    player_name: str,
    player_elo: int,
    today: date,
) -> None:
    lines += [
        f"# 🎯 Plan d'entraînement — {today.strftime('%d %B %Y')}",
        "",
        "---",
        "",
        f"| 👤 Joueur | 📊 Elo | 🗓️ Thème de la semaine |",
        f"|---|---|---|",
        f"| **{player_name or '—'}** | **{player_elo}** | {plan.get('week_theme', '')} |",
        "",
    ]


def _analysis_summary(lines: list[str], profile: WeaknessProfile) -> None:
    lines += [
        "## 📋 Résumé d'analyse",
        "",
    ]

    cats = profile["category_breakdown"]
    phase_icon = _PHASE_ICON.get(profile["weakest_phase"], "")

    lines += [
        "| Indicateur | Valeur |",
        "|---|---|",
        f"| Parties analysées | **{profile['total_games']}** |",
        f"| ACPL proxy moyen | **{profile['avg_acpl']:.1f}** |",
        f"| {_CATEGORY_ICON['blunder']} Gaffes | {cats.get('blunder', 0)} |",
        f"| {_CATEGORY_ICON['mistake']} Erreurs | {cats.get('mistake', 0)} |",
        f"| {_CATEGORY_ICON['dubious']} Coups douteux | {cats.get('dubious', 0)} |",
        f"| Phase la plus faible | {phase_icon} **{profile['weakest_phase'].capitalize()}** |",
        "",
    ]

    # Erreurs par phase
    if profile["phase_breakdown"]:
        lines += [
            "### Erreurs par phase",
            "",
            "| Phase | Erreurs | ACPL proxy |",
            "|---|---|---|",
        ]
        for phase, count in sorted(
            profile["phase_breakdown"].items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            avg = profile["avg_cp_loss_by_phase"].get(phase, 0.0)
            icon = _PHASE_ICON.get(phase, "")
            lines.append(f"| {icon} {phase.capitalize()} | {count} | {avg:.0f} cp |")
        lines.append("")

    # Ouvertures problématiques
    if profile["problematic_openings"]:
        lines += [
            "### Ouvertures problématiques",
            "",
            "| ECO | Ouverture | Erreurs |",
            "|---|---|---|",
        ]
        for eco, opening_name, count in profile["problematic_openings"]:
            lines.append(f"| `{eco}` | {opening_name} | {count} |")
        lines.append("")

    # Positions clés
    if profile["worst_positions"]:
        lines += [
            "### 🔎 Positions clés à retravailler",
            "",
            "> Les FEN ci-dessous correspondent à la position **avant** le coup fautif.",
            "> Reproduisez-les sur un échiquier pour vous corriger.",
            "",
        ]
        for i, err in enumerate(profile["worst_positions"][:5], 1):
            icon = _CATEGORY_ICON.get(err.category, "")
            label = _CATEGORY_LABEL.get(err.category, err.category)
            phase_icon = _PHASE_ICON.get(err.phase, "")
            lines += [
                f"#### Position {i} — coup {err.move_number}, "
                f"{phase_icon} {err.phase.capitalize()}",
                "",
                f"| | |",
                f"|---|---|",
                f"| Coup joué | `{err.played}` → {icon} **{label}** |",
                f"| Meilleur coup | `{err.best}`  |" if err.best
                else "| Meilleur coup | *non disponible* |",
            ]
            if err.comment:
                lines.append(f"| Commentaire caissAI | *{err.comment}* |")
            lines += [
                f"| FEN | `{err.fen}` |",
                "",
                f"[![Analyser sur Lichess]"
                f"(https://img.shields.io/badge/Analyser-Lichess-green)]"
                f"(https://lichess.org/analysis/{err.fen.replace(' ', '_')})",
                "",
            ]


def _weekly_plan(lines: list[str], plan: TrainingPlan) -> None:
    lines += [
        "---",
        "",
        "## 📅 Plan hebdomadaire",
        "",
    ]

    key_concepts = plan.get("key_concepts", [])
    if key_concepts:
        lines += [
            "> **Concepts clés de la semaine :**",
            "> " + " · ".join(f"*{c}*" for c in key_concepts),
            "",
        ]

    for day_task in plan.get("daily_tasks", []):
        day = day_task.get("day", "")
        focus = day_task.get("focus", "")
        exercises = day_task.get("exercises", [])
        total_min = sum(ex.get("duration_min", 0) for ex in exercises)

        lines += [
            f"### {day} — {focus}",
            "",
            f"*Durée totale : **{total_min} min***",
            "",
        ]
        for ex in exercises:
            ex_type = ex.get("type", "")
            description = ex.get("description", "")
            duration = ex.get("duration_min", 0)
            url = ex.get("lichess_url", "")
            icon = _EXERCISE_ICON.get(ex_type, "▸")

            lines.append(f"{icon} **{description}** — *{duration} min*")
            if url:
                lines.append(f"   → [{url}]({url})")
        lines.append("")

    success = plan.get("success_metrics", "")
    if success:
        lines += [
            "---",
            "",
            "## 🏆 Objectifs de la semaine",
            "",
            f"> {success}",
            "",
        ]


def _gm_studies(
    lines: list[str], gm_studies: list[OpeningStudy] | None
) -> None:
    if not gm_studies:
        return

    lines += [
        "---",
        "",
        "## ♟️ Parties de grands maîtres à étudier",
        "",
        "> Ces parties ont été sélectionnées par l'Opening Explorer Lichess "
        "sur vos ouvertures problématiques.",
        "",
    ]
    for study in gm_studies:
        lines += [
            f"### `{study.eco}` — {study.opening_name}",
            "",
            f"[📚 Explorer cette ouverture sur Lichess]"
            f"(https://lichess.org/opening/{study.eco})",
            "",
        ]
        for g in study.games:
            result = _RESULT_LABEL.get(g.winner, "?")
            lines.append(
                f"- [{g.white} vs {g.black} ({g.year}) **{result}**]"
                f"(https://lichess.org/{g.game_id})"
            )
        lines.append("")


def _review(lines: list[str]) -> None:
    lines += [
        "---",
        "",
        "## 📝 Bilan de semaine",
        "",
        "> *À remplir en fin de semaine avant de lancer la session suivante.*",
        "",
        "### ✅ Objectifs atteints",
        "",
        "- [ ] *(compléter)*",
        "",
        "### ⚠️ Difficultés rencontrées",
        "",
        "*(compléter)*",
        "",
        "### 💡 Notes pour la session suivante",
        "",
        "*(compléter)*",
        "",
    ]
