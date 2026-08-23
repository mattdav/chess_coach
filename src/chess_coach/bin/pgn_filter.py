"""Filtrage déclaratif des parties PGN selon un profil YAML.

Le filtre est chargé depuis ``config/pgn_filter.yaml``. Tous les critères
sont combinés en ET (une partie doit satisfaire TOUS les critères actifs).
À l'intérieur d'une liste (events, results, keywords), les valeurs sont en OU.

Critères disponibles :
    player.name        Nom du joueur (correspondance partielle, insensible à la casse)
    player.color       Côté du joueur : "white" | "black" | "both"
    events             Liste de mots-clés sur le header [Event]
    date.from / to     Fenêtre de dates (format PGN : "YYYY.MM.DD")
    results            Liste de résultats admis : "1-0", "0-1", "1/2-1/2"
    min_opponent_elo   Elo minimum de l'adversaire (0 = pas de filtre)
    keywords           Mots-clés libres dans n'importe quel header
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chess.pgn
import yaml


@dataclass
class PgnFilter:
    """Critères de sélection des parties PGN.

    Tous les champs sont optionnels. Un champ absent ou vide désactive
    le critère correspondant.

    Examples:
        >>> f = PgnFilter()
        >>> f.player_name
        ''
        >>> f.is_active
        False
    """

    player_name: str = ""
    player_color: str = "both"  # "white" | "black" | "both"
    events: list[str] = field(default_factory=list)
    date_from: str = ""  # "YYYY.MM.DD" ou préfixe "YYYY"
    date_to: str = ""
    results: list[str] = field(default_factory=list)
    min_opponent_elo: int = 0
    keywords: list[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        """Retourne True si au moins un critère est actif.

        Examples:
            >>> PgnFilter().is_active
            False
            >>> PgnFilter(player_name="Dupont").is_active
            True
        """
        return bool(
            self.player_name
            or self.events
            or self.date_from
            or self.date_to
            or self.results
            or self.min_opponent_elo > 0
            or self.keywords
        )


def load_filter(path: Path) -> PgnFilter:
    """Charge un filtre PGN depuis un fichier YAML.

    Args:
        path: Chemin vers ``pgn_filter.yaml``.

    Returns:
        Instance de :class:`PgnFilter`. Si le fichier est absent ou vide,
        retourne un filtre inactif (aucun critère).

    Examples:
        >>> import tempfile, pathlib, textwrap
        >>> yaml_content = textwrap.dedent('''
        ...     player:
        ...       name: "Dupont"
        ...     results: ["1-0"]
        ... ''')
        >>> with tempfile.NamedTemporaryFile(
        ...     mode='w', suffix='.yaml', delete=False, encoding='utf-8'
        ... ) as f:
        ...     _ = f.write(yaml_content)
        ...     tmp = pathlib.Path(f.name)
        >>> pgn_filter = load_filter(tmp)
        >>> pgn_filter.player_name
        'Dupont'
        >>> pgn_filter.results
        ['1-0']
        >>> tmp.unlink()
    """
    if not path.exists():
        logging.info("load_filter : %s absent — filtre inactif.", path.name)
        return PgnFilter()

    with path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}

    player_section = data.get("player") or {}
    date_section = data.get("date") or {}

    return PgnFilter(
        player_name=str(player_section.get("name", "") or "").strip(),
        player_color=str(player_section.get("color", "both") or "both").strip(),
        events=[str(e) for e in (data.get("events") or []) if e],
        date_from=str(date_section.get("from", "") or "").strip(),
        date_to=str(date_section.get("to", "") or "").strip(),
        results=[str(r) for r in (data.get("results") or []) if r],
        min_opponent_elo=int(data.get("min_opponent_elo") or 0),
        keywords=[str(k) for k in (data.get("keywords") or []) if k],
    )


def matches(game: chess.pgn.Game, pgn_filter: PgnFilter) -> bool:
    """Vérifie si une partie satisfait tous les critères du filtre.

    Args:
        game: Partie PGN à tester.
        pgn_filter: Critères de sélection.

    Returns:
        True si la partie satisfait tous les critères actifs.

    Examples:
        >>> import chess.pgn
        >>> game = chess.pgn.Game()
        >>> game.headers.update({
        ...     "White": "Dupont, Jean",
        ...     "Black": "Martin, Paul",
        ...     "Event": "Championnat régional",
        ...     "Date": "2024.03.15",
        ...     "Result": "1-0",
        ...     "WhiteElo": "1800",
        ...     "BlackElo": "1650",
        ... })
        >>> matches(game, PgnFilter())
        True
        >>> matches(game, PgnFilter(player_name="Dupont"))
        True
        >>> matches(game, PgnFilter(player_name="Dupont", player_color="black"))
        False
        >>> matches(game, PgnFilter(results=["0-1"]))
        False
        >>> matches(game, PgnFilter(date_from="2025.01.01"))
        False
        >>> matches(game, PgnFilter(min_opponent_elo=1700, player_name="Dupont"))
        False
        >>> matches(game, PgnFilter(min_opponent_elo=1600, player_name="Dupont"))
        True
        >>> # sans player_name, l'adversaire n'est pas déterminable : le
        >>> # critère Elo est silencieusement ignoré.
        >>> matches(game, PgnFilter(min_opponent_elo=1700))
        True
    """
    if not pgn_filter.is_active:
        return True

    headers = game.headers
    white = headers.get("White", "")
    black = headers.get("Black", "")

    # ── Filtre joueur ──────────────────────────────────────────────────────
    if pgn_filter.player_name:
        name_lower = pgn_filter.player_name.lower()
        color = pgn_filter.player_color

        plays_white = name_lower in white.lower()
        plays_black = name_lower in black.lower()

        if color == "white" and not plays_white:
            return False
        if color == "black" and not plays_black:
            return False
        if color == "both" and not (plays_white or plays_black):
            return False

    # ── Filtre tournoi ─────────────────────────────────────────────────────
    if pgn_filter.events:
        event = headers.get("Event", "").lower()
        if not any(e.lower() in event for e in pgn_filter.events):
            return False

    # ── Filtre date ────────────────────────────────────────────────────────
    date_str = headers.get("Date", "")
    # Normalise "????" et dates partielles
    date_clean = date_str.replace("?", "0").replace(" ", "")

    if pgn_filter.date_from:
        from_clean = pgn_filter.date_from.replace("?", "0")
        if date_clean < from_clean:
            return False

    if pgn_filter.date_to:
        to_clean = pgn_filter.date_to.replace("?", "0")
        if date_clean > to_clean:
            return False

    # ── Filtre résultat ────────────────────────────────────────────────────
    if pgn_filter.results:
        if headers.get("Result", "") not in pgn_filter.results:
            return False

    # ── Filtre Elo adversaire ──────────────────────────────────────────────
    if pgn_filter.min_opponent_elo > 0 and pgn_filter.player_name:
        name_lower = pgn_filter.player_name.lower()
        plays_white = name_lower in white.lower()

        opponent_elo_str = (
            headers.get("BlackElo", "0")
            if plays_white
            else headers.get("WhiteElo", "0")
        )

        try:
            opponent_elo = int(opponent_elo_str or "0")
        except ValueError:
            opponent_elo = 0

        if opponent_elo < pgn_filter.min_opponent_elo:
            return False

    # ── Filtre mots-clés libres ────────────────────────────────────────────
    if pgn_filter.keywords:
        all_headers = " ".join(str(v) for v in headers.values()).lower()
        if not any(k.lower() in all_headers for k in pgn_filter.keywords):
            return False

    return True


def apply_filter(
    games: list[chess.pgn.Game],
    pgn_filter: PgnFilter,
) -> list[chess.pgn.Game]:
    """Applique un filtre sur une liste de parties.

    Args:
        games: Liste de parties à filtrer.
        pgn_filter: Critères de sélection.

    Returns:
        Sous-liste des parties satisfaisant tous les critères.

    Examples:
        >>> apply_filter([], PgnFilter())
        []
    """
    if not pgn_filter.is_active:
        return games

    filtered = [g for g in games if matches(g, pgn_filter)]
    logging.info(
        "apply_filter : %d/%d parties retenues",
        len(filtered),
        len(games),
    )
    return filtered
