"""Collecte de parties depuis des fichiers PGN locaux (parties officielles).

Ces parties sont typiquement exportées depuis ChessBase (.2cbh → PGN)
et analysées par caissAI avec ``comment=True`` (résumé GPT complet).

Le filtre déclaratif ``config/pgn_filter.yaml`` permet de sélectionner
précisément quelles parties inclure dans l'analyse (par joueur, tournoi,
date, résultat, Elo adversaire ou mots-clés libres).
"""

import io
import logging
from pathlib import Path

import chess.pgn

from chess_coach.bin.pgn_filter import PgnFilter, apply_filter, load_filter


def read_games_from_file(pgn_path: Path) -> list[chess.pgn.Game]:
    """Lit toutes les parties d'un fichier PGN multi-parties.

    Args:
        pgn_path: Chemin vers le fichier PGN.

    Returns:
        Liste des parties valides dans l'ordre de lecture.

    Examples:
        >>> import tempfile, pathlib
        >>> with tempfile.NamedTemporaryFile(suffix=".pgn", delete=False,
        ...     mode="w", encoding="utf-8") as f:
        ...     _ = f.write("")
        ...     tmp = pathlib.Path(f.name)
        >>> read_games_from_file(tmp)
        []
        >>> tmp.unlink()
    """
    return _read_pgn_file(pgn_path)


def select_games(
    games: list[chess.pgn.Game],
    indices: list[int] | None = None,
    player: str | None = None,
) -> list[tuple[int, chess.pgn.Game]]:
    """Filtre et sélectionne des parties depuis une liste.

    Args:
        games: Toutes les parties du fichier.
        indices: Indices 1-basés des parties à traiter. None = toutes.
        player: Si fourni, ne retient que les parties où ce joueur apparaît
            (correspondance partielle, insensible à la casse) dans White ou Black.

    Returns:
        Liste de (index_1_basé, partie) pour les parties sélectionnées.

    Examples:
        >>> select_games([])
        []
    """
    selected: list[tuple[int, chess.pgn.Game]] = []
    for i, game in enumerate(games, start=1):
        if indices is not None and i not in indices:
            continue
        if player:
            white = game.headers.get("White", "").lower()
            black = game.headers.get("Black", "").lower()
            if player.lower() not in white and player.lower() not in black:
                continue
        selected.append((i, game))
    return selected


def list_games(games: list[chess.pgn.Game]) -> None:
    """Affiche la liste numérotée des parties d'un fichier.

    Args:
        games: Parties à lister.

    Examples:
        >>> list_games([])
        0 partie(s) trouvée(s).
    """
    print(f"{len(games)} partie(s) trouvée(s).\n")
    for i, game in enumerate(games, start=1):
        white = game.headers.get("White", "?")
        black = game.headers.get("Black", "?")
        date = game.headers.get("Date", "?")
        event = game.headers.get("Event", "?")
        result = game.headers.get("Result", "?")
        opening = game.headers.get("Opening", "")
        opening_str = f"  {opening}" if opening else ""
        print(f"  [{i:3d}] {white} vs {black}  {result}  {date}  {event}{opening_str}")


def load_pgn_files(
    pgn_paths: list[Path],
    pgn_filter: PgnFilter | None = None,
    recursive: bool = False,
) -> list[chess.pgn.Game]:
    """Charge et filtre les parties depuis des fichiers ou dossiers PGN.

    Args:
        pgn_paths: Liste de chemins vers des fichiers ``.pgn`` ou des dossiers.
            Les dossiers sont parcourus récursivement si ``recursive=True``.
        pgn_filter: Critères de sélection déclaratifs. Si None, toutes les
            parties sont retenues. Charger via :func:`~pgn_filter.load_filter`.
        recursive: Si True, parcourt les sous-dossiers.

    Returns:
        Liste de parties PGN valides satisfaisant le filtre, dans l'ordre
        de lecture.

    Examples:
        >>> load_pgn_files([])
        []
    """
    if not pgn_paths:
        return []

    all_files: list[Path] = []
    for path in pgn_paths:
        if path.is_file() and path.suffix.lower() == ".pgn":
            all_files.append(path)
        elif path.is_dir():
            pattern = "**/*.pgn" if recursive else "*.pgn"
            all_files.extend(sorted(path.glob(pattern)))
        else:
            logging.warning("load_pgn_files : chemin ignoré (introuvable) : %s", path)

    games: list[chess.pgn.Game] = []
    for pgn_file in all_files:
        file_games = _read_pgn_file(pgn_file)
        if pgn_filter and pgn_filter.is_active:
            before = len(file_games)
            file_games = apply_filter(file_games, pgn_filter)
            logging.info(
                "load_pgn_files : %s — %d/%d partie(s) retenues après filtre",
                pgn_file.name,
                len(file_games),
                before,
            )
            print(
                f"    {pgn_file.name} : {len(file_games)}/{before} partie(s) "
                "retenues après filtre"
            )
        else:
            logging.info(
                "load_pgn_files : %d partie(s) chargée(s) depuis %s",
                len(file_games),
                pgn_file.name,
            )
            print(f"    {pgn_file.name} : {len(file_games)} partie(s) chargée(s)")

        games.extend(file_games)

    logging.info(
        "load_pgn_files : %d partie(s) au total depuis %d fichier(s)",
        len(games),
        len(all_files),
    )
    return games


def load_pgn_files_with_config(
    pgn_paths: list[Path],
    filter_config_path: Path | None = None,
    recursive: bool = False,
) -> list[chess.pgn.Game]:
    """Charge les parties PGN en appliquant le filtre depuis ``pgn_filter.yaml``.

    Raccourci qui charge le filtre depuis le fichier YAML avant d'appeler
    :func:`load_pgn_files`. Utilisé par ``main.py``.

    Args:
        pgn_paths: Fichiers ou dossiers PGN à charger.
        filter_config_path: Chemin vers ``pgn_filter.yaml``. Si None, cherche
            dans le dossier ``config/`` du package.
        recursive: Si True, parcourt les sous-dossiers.

    Returns:
        Liste de parties filtrées.

    Examples:
        >>> load_pgn_files_with_config([])
        []
    """
    if not pgn_paths:
        return []

    if filter_config_path is None:
        filter_config_path = Path(__file__).parent.parent / "config" / "pgn_filter.yaml"

    pgn_filter = load_filter(filter_config_path)

    if pgn_filter.is_active:
        active_criteria = []
        if pgn_filter.player_name:
            active_criteria.append(f"joueur='{pgn_filter.player_name}'")
        if pgn_filter.events:
            active_criteria.append(f"tournois={pgn_filter.events}")
        if pgn_filter.date_from or pgn_filter.date_to:
            active_criteria.append(
                f"dates=[{pgn_filter.date_from or '…'}→{pgn_filter.date_to or '…'}]"
            )
        if pgn_filter.results:
            active_criteria.append(f"résultats={pgn_filter.results}")
        if pgn_filter.min_opponent_elo:
            active_criteria.append(f"elo_adversaire≥{pgn_filter.min_opponent_elo}")
        if pgn_filter.keywords:
            active_criteria.append(f"mots-clés={pgn_filter.keywords}")
        print(f"    Filtre PGN actif : {' | '.join(active_criteria)}")
    else:
        print("    Aucun filtre PGN — toutes les parties chargées")

    return load_pgn_files(pgn_paths, pgn_filter=pgn_filter, recursive=recursive)


def _read_pgn_file(path: Path) -> list[chess.pgn.Game]:
    """Lit toutes les parties d'un fichier PGN.

    Args:
        path: Chemin vers le fichier PGN.

    Returns:
        Liste de parties valides du fichier.

    Examples:
        >>> import tempfile, pathlib
        >>> with tempfile.NamedTemporaryFile(suffix=".pgn", delete=False,
        ...     mode="w", encoding="utf-8") as f:
        ...     _ = f.write("")
        ...     tmp = pathlib.Path(f.name)
        >>> _read_pgn_file(tmp)
        []
        >>> tmp.unlink()
    """
    games: list[chess.pgn.Game] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        stream = io.StringIO(content)
        while True:
            game = chess.pgn.read_game(stream)
            if game is None:
                break
            games.append(game)
    except OSError as exc:
        logging.error("_read_pgn_file : impossible de lire %s : %s", path, exc)
    return games
