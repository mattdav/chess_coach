"""Orchestrateur de session de coaching."""

import logging
import os
from pathlib import Path

import chess.pgn

from chess_coach.bin.analyzer import GameReport, report_from_pgn
from chess_coach.bin.coach import TrainingPlan, generate_weekly_plan
from chess_coach.bin.gm_games import fetch_opening_studies
from chess_coach.bin.pattern_detector import WeaknessProfile, build_weakness_profile
from chess_coach.bin.podcast_generator import generate_podcasts
from chess_coach.bin.report_writer import write_training_plan
from chess_coach.bin.tracker import get_progress_trend, init_db, save_snapshot


def run_session(
    pgn_games: list[chess.pgn.Game],
    player_elo: int,
    player_name: str = "",
    lichess_token: str = "",
    caissai_config_path: Path | None = None,
    max_daily_minutes: int = 45,
    db_path: str | Path = "src/chess_coach/data/chess_coach.db",
    output_dir: Path | None = None,
    podcast_dir: Path | None = None,
    max_podcasts: int = 3,
    dry_run: bool = False,
    generate_podcast: bool = False,
    model: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
) -> tuple[WeaknessProfile, TrainingPlan | None]:
    """Exécute une session de coaching depuis des parties déjà annotées par caissAI.

    Pipeline en 4 étapes :
    1. Extraction des erreurs depuis les PGN annotés (NAGs caissAI)
    2. Profil de faiblesses agrégé
    3. Parties GM Lichess Masters + plan Claude + livrable Markdown
    4. Podcasts podgenai (optionnel) + persistance SQLite

    Args:
        pgn_games: Parties PGN déjà annotées par caissAI.
        player_elo: Elo courant.
        player_name: Nom du joueur pour filtrer ses erreurs (correspondance
            partielle). Si vide, toutes les erreurs sont remontées.
        max_daily_minutes: Durée max entraînement par jour (pour Claude).
        db_path: Chemin vers la base SQLite.
        lichess_token: Token Lichess OAuth pour récupérer les parties GM
            (générer sur https://lichess.org/account/oauth/token).
            Si vide, l'étape parties GM est ignorée.
        output_dir: Dossier de sortie pour le plan Markdown et les podcasts.
            Si None, utilise ``src/chess_coach/data/plans/``.
        podcast_dir: Dossier de sortie des MP3 podgenai (override output_dir).
        max_podcasts: Nombre maximum de podcasts à générer.
        dry_run: Extrait les erreurs sans appel Claude ni écriture SQLite.
        generate_podcast: Active la génération de podcasts podgenai.
        model: Modèle Claude. Défaut : ANTHROPIC_MODEL dans .env,
            sinon "claude-sonnet-4-5".

    Returns:
        Tuple (WeaknessProfile, TrainingPlan | None).
    """
    if not pgn_games:
        print("Aucune partie fournie.")
        return build_weakness_profile([]), None

    plans_dir = output_dir or Path("src/chess_coach/data/plans")

    # 1. Extraction des erreurs depuis les PGN annotés
    total = len(pgn_games)
    print(f"1/4 - Extraction des erreurs depuis {total} partie(s) annotée(s)...")
    reports: list[GameReport] = []
    for i, game in enumerate(pgn_games, 1):
        try:
            report = report_from_pgn(game, player_name=player_name)
            reports.append(report)
            print(f"    {i:3d}/{total} OK  erreurs : {len(report.errors)}")
        except Exception as exc:
            logging.warning("Partie %d/%d ignorée : %s", i, total, exc)
            print(f"    {i:3d}/{total} IGNORE  ({exc})")

    print(f"    {len(reports)}/{total} partie(s) traitée(s) avec succès")

    # 2. Profil de faiblesses
    print("2/4 - Construction du profil de faiblesses...")
    profile = build_weakness_profile(reports)
    _print_profile_summary(profile)

    if dry_run:
        print("3/4 - Dry-run : parties GM, plan et sauvegarde ignorés.")
        return profile, None

    # 3. Parties GM + Plan Claude + livrable Markdown
    print("3/4 - Parties de grands maîtres (Lichess Masters API)...")
    gm_studies = fetch_opening_studies(
        problematic_openings=profile["problematic_openings"],
        lichess_token=lichess_token,
        caissai_config_path=caissai_config_path,
        max_games_per_opening=3,
        max_openings=3,
    )
    if gm_studies:
        total_gm = sum(len(s.games) for s in gm_studies)
        print(
            f"    {total_gm} partie(s) GM récupérée(s)"
            f" sur {len(gm_studies)} ouverture(s)"
        )
    else:
        print("    Aucune partie GM (codes ECO non résolus ou API indisponible)")

    print("4/4 - Génération du plan d'entraînement (Claude)...")
    plan = generate_weekly_plan(
        profile,
        player_elo=player_elo,
        max_daily_minutes=max_daily_minutes,
        model=model,
        gm_studies=gm_studies if gm_studies else None,
    )
    _print_plan_summary(plan)

    plan_path = write_training_plan(
        profile=profile,
        plan=plan,
        player_name=player_name,
        player_elo=player_elo,
        output_dir=plans_dir,
        gm_studies=gm_studies if gm_studies else None,
    )
    print(f"    Plan écrit : {plan_path}")

    # 4. Podcasts + persistance SQLite
    if generate_podcast:
        pod_dir = podcast_dir or plans_dir / "podcasts"
        generate_podcasts(plan, player_elo, pod_dir, max_topics=max_podcasts)
    else:
        print("    Podcasts désactivés (passer --podcast pour activer)")

    conn = init_db(db_path)
    save_snapshot(conn, player_elo, profile, plan)
    trend = get_progress_trend(conn, weeks=4)
    conn.close()

    if len(trend) >= 2:
        prev = trend[1].get("acpl")
        curr = trend[0].get("acpl")
        if isinstance(prev, float) and isinstance(curr, float):
            delta = curr - prev
            direction = "amélioration" if delta < 0 else "régression"
            print(
                f"\nTendance : {direction} de {abs(delta):.1f} pts ACPL"
                " vs semaine précédente"
            )

    return profile, plan


def _print_profile_summary(profile: WeaknessProfile) -> None:
    """Affiche un résumé lisible du profil de faiblesses."""
    cats = profile["category_breakdown"]
    print(f"\n{'─' * 55}")
    print(f"  Parties analysées  : {profile['total_games']}")
    print(f"  ACPL proxy moyen   : {profile['avg_acpl']:.1f}")
    print(
        f"  Erreurs caissAI    : "
        f"{cats.get('blunder', 0)} blunders  "
        f"{cats.get('mistake', 0)} mistakes  "
        f"{cats.get('dubious', 0)} douteux"
    )
    print(f"  Phase la plus faible : {profile['weakest_phase']}")
    print("  Erreurs par phase :")
    for phase, count in profile["phase_breakdown"].items():
        avg = profile["avg_cp_loss_by_phase"].get(phase, 0.0)
        print(f"    {phase:12s} : {count:3d} erreur(s)  (proxy {avg:.0f} cp)")
    if profile["problematic_openings"]:
        print("  Ouvertures problématiques :")
        for eco, opening_name, count in profile["problematic_openings"][:3]:
            label = f"{eco} — {opening_name}" if opening_name != eco else eco
            print(f"    {label[:45]:45s} : {count}")
    print(f"{'─' * 55}\n")


def _print_plan_summary(plan: TrainingPlan) -> None:
    """Affiche un résumé lisible du plan d'entraînement."""
    print(f"\n{'=' * 55}")
    print(f"  PLAN : {plan['week_theme']}")
    print(f"{'=' * 55}")
    for day in plan.get("daily_tasks", []):
        total = sum(ex.get("duration_min", 0) for ex in day.get("exercises", []))
        print(f"  {day['day']:10s} ({total:2d} min)  {day['focus']}")
    concepts = ", ".join(plan.get("key_concepts", []))
    print(f"\n  Concepts clés : {concepts}")
    print(f"  Succès        : {plan.get('success_metrics', '')}")
    print()
