"""Point d'entrée CLI de chess_coach."""

import argparse
import importlib.resources
import logging
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _get_package_dir(folder_name: str) -> Path:
    """Retourne le chemin absolu d'un sous-dossier du package.

    Args:
        folder_name: Nom du sous-dossier (``data``, ``log``).

    Returns:
        Chemin vers le dossier.

    Raises:
        NameError: Si le dossier n'existe pas dans le package.
    """
    try:
        with importlib.resources.path(f"chess_coach.{folder_name}", "") as p:
            return Path(p)
    except (NameError, ModuleNotFoundError) as exc:
        raise NameError(f"Dossier introuvable : {folder_name}") from exc


def _setup_logging(log_path: Path) -> None:
    """Configure le logger applicatif."""
    log_path.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path / "chess_coach.log"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )


def main() -> None:
    """Point d'entrée CLI enregistré dans ``pyproject.toml``."""
    env_file = find_dotenv(usecwd=True) or str(
        Path(__file__).parent.parent.parent / ".env"
    )
    load_dotenv(env_file)

    # Chargement de la config joueur pour alimenter les défauts CLI
    from chess_coach.bin.player_config import load_player_config

    player_cfg = load_player_config()

    # ── Parser ────────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        prog="chess_coach",
        description=(
            "Coach d'échecs IA — lit des parties déjà annotées par caissAI\n"
            "et génère un plan d'entraînement Claude.\n\n"
            "Exemples :\n"
            '  chess_coach --pgn "C:/parties/mes parties.pgn" --list\n'
            '  chess_coach --pgn "C:/parties/mes parties.pgn" --games 3 7\n'
            '  chess_coach --pgn "C:/parties/mes parties.pgn"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pgn",
        metavar="CHEMIN",
        required=True,
        help=(
            "Fichier PGN annoté par caissAI (peut contenir plusieurs parties). "
            'Ex : --pgn "C:/ChessBase/mes parties.pgn"'
        ),
    )
    parser.add_argument(
        "--games",
        metavar="N",
        nargs="+",
        type=int,
        default=None,
        help=(
            "Indices 1-basés des parties à analyser. "
            "Ex : --games 3  ou  --games 1 5 12. "
            "Sans cet argument, toutes les parties du fichier sont analysées. "
            "Utilisez --list pour connaître les indices."
        ),
    )
    parser.add_argument(
        "--player",
        metavar="NOM",
        default=os.environ.get("PLAYER_NAME", player_cfg.name) or None,
        help=(
            "Nom du joueur — filtre les erreurs à ses coups uniquement. "
            f"Défaut : player_config.yaml → '{player_cfg.name}'. "
            "Surchargeable via PLAYER_NAME dans .env."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Affiche la liste numérotée des parties du fichier --pgn et quitte.",
    )
    parser.add_argument(
        "--elo",
        type=int,
        default=int(os.environ.get("PLAYER_ELO", player_cfg.elo)),
        help=(
            f"Elo courant. Défaut : player_config.yaml → {player_cfg.elo}. "
            "Surchargeable via PLAYER_ELO dans .env."
        ),
    )
    parser.add_argument(
        "--podcast",
        action="store_true",
        help="Générer des podcasts podgenai sur les sujets du plan d'entraînement",
    )
    parser.add_argument(
        "--podcast-dir",
        default=None,
        metavar="CHEMIN",
        help="Dossier de sortie des MP3 podgenai",
    )
    parser.add_argument(
        "--max-podcasts",
        type=int,
        default=3,
        metavar="N",
        help="Nombre maximum de podcasts à générer (défaut : 3)",
    )
    parser.add_argument(
        "--max-minutes",
        type=int,
        default=45,
        metavar="N",
        help="Durée max entraînement/jour en minutes (défaut : 45)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extrait les erreurs sans appel Claude ni écriture SQLite",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="CHEMIN",
        help=(
            "Dossier de sortie pour le plan Markdown et les podcasts "
            "(défaut : data/plans/)"
        ),
    )
    args = parser.parse_args()

    # ── Validation du fichier PGN ─────────────────────────────────────────
    pgn_path = Path(args.pgn)
    if not pgn_path.exists():
        parser.error(f"Fichier introuvable : {pgn_path}")

    # ── Mode --list : ne nécessite aucune clé API, on sort tôt ───────────
    if args.list:
        from chess_coach.bin.pgn_collector import list_games, read_games_from_file

        list_games(read_games_from_file(pgn_path))
        sys.exit(0)

    # ── Variables d'environnement obligatoires ────────────────────────────
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    lichess_token = os.environ.get("LICHESS_TOKEN", "")
    caissai_config_str = os.environ.get("CAISSAI_CONFIG_PATH", "")
    caissai_config_path = Path(caissai_config_str) if caissai_config_str else None
    if not anthropic_key:
        parser.error("Variable d'environnement manquante dans .env : ANTHROPIC_API_KEY")
    if not lichess_token:
        print(
            "    Avertissement : LICHESS_TOKEN absent du .env — "
            "les parties de grands maîtres seront ignorées.\n"
            "    Générer un token sur https://lichess.org/account/oauth/token"
        )

    # ── Logging et chemins runtime ────────────────────────────────────────
    try:
        log_path = _get_package_dir("log")
    except NameError:
        log_path = Path("src/chess_coach/log")
    _setup_logging(log_path)

    try:
        data_path = _get_package_dir("data")
    except NameError:
        data_path = Path("src/chess_coach/data")

    db_path = data_path / "chess_coach.db"
    output_dir = Path(args.output_dir) if args.output_dir else data_path / "plans"

    # ── Sélection des parties ─────────────────────────────────────────────
    from chess_coach.bin.pgn_collector import read_games_from_file, select_games

    all_games = read_games_from_file(pgn_path)
    if not all_games:
        parser.error(f"Aucune partie trouvée dans {pgn_path}")

    selected = select_games(all_games, indices=args.games, player=args.player)
    if not selected:
        parser.error("Aucune partie ne correspond aux critères (--games / --player).")

    n_total = len(all_games)
    n_selected = len(selected)
    suffix = f" (indices : {args.games})" if args.games else ""
    player_suffix = f" — joueur : {args.player}" if args.player else ""
    print(
        f"{n_selected}/{n_total} partie(s) sélectionnée(s)"
        f" dans {pgn_path.name}{suffix}{player_suffix}"
    )

    pgn_games = [game for _, game in selected]

    # ── Lancement ─────────────────────────────────────────────────────────
    from chess_coach.bin.session import run_session

    try:
        run_session(
            pgn_games=pgn_games,
            player_elo=args.elo,
            player_name=args.player or "",
            lichess_token=lichess_token,
            caissai_config_path=caissai_config_path,
            max_daily_minutes=args.max_minutes,
            db_path=db_path,
            output_dir=output_dir,
            podcast_dir=Path(args.podcast_dir) if args.podcast_dir else None,
            max_podcasts=args.max_podcasts,
            dry_run=args.dry_run,
            generate_podcast=args.podcast,
        )
    except KeyboardInterrupt:
        print("\nInterrompu.")
        sys.exit(0)
    except Exception:
        logging.exception("Erreur fatale.")
        sys.exit(1)


if __name__ == "__main__":
    main()
