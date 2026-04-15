"""Lecture de la configuration joueur depuis ``config/player_config.yaml``.

Ce module expose :
- ``PlayerConfig`` : dataclass avec nom et elo du joueur
- ``load_player_config()`` : charge le fichier YAML et retourne un PlayerConfig
- ``load_pgn_filter_from_config()`` : construit un PgnFilter depuis le même fichier
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from chess_coach.bin.pgn_filter import PgnFilter


@dataclass
class PlayerConfig:
    """Configuration personnelle du joueur.

    Examples:
        >>> cfg = PlayerConfig(name="Dupont", elo=1650)
        >>> cfg.name
        'Dupont'
        >>> cfg.elo
        1650
    """

    name: str = ""
    elo: int = 1500


def load_player_config(config_path: Path | None = None) -> PlayerConfig:
    """Charge la configuration joueur depuis ``player_config.yaml``.

    Args:
        config_path: Chemin vers le fichier YAML. Si None, cherche dans
            le dossier ``config/`` du package.

    Returns:
        :class:`PlayerConfig` rempli. Retourne des valeurs par défaut si
        le fichier est absent.

    Examples:
        >>> import tempfile, pathlib, textwrap
        >>> yaml_content = textwrap.dedent('''
        ...     player:
        ...       name: "Dupont"
        ...       elo: 1700
        ... ''')
        >>> with tempfile.NamedTemporaryFile(
        ...     mode='w', suffix='.yaml', delete=False, encoding='utf-8'
        ... ) as f:
        ...     _ = f.write(yaml_content)
        ...     tmp = pathlib.Path(f.name)
        >>> cfg = load_player_config(tmp)
        >>> cfg.name
        'Dupont'
        >>> cfg.elo
        1700
        >>> tmp.unlink()
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "player_config.yaml"

    if not config_path.exists():
        logging.info(
            "load_player_config : %s absent — valeurs par défaut.", config_path.name
        )
        return PlayerConfig()

    with config_path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}

    player_section = data.get("player") or {}
    return PlayerConfig(
        name=str(player_section.get("name", "") or "").strip(),
        elo=int(player_section.get("elo", 1500) or 1500),
    )


def load_pgn_filter_from_config(config_path: Path | None = None) -> PgnFilter:
    """Construit un PgnFilter depuis ``player_config.yaml``.

    Lit les critères de filtrage (events, date, results, min_opponent_elo,
    keywords) ainsi que le nom du joueur pour les construire en PgnFilter.

    Args:
        config_path: Chemin vers le fichier YAML. Si None, cherche dans
            le dossier ``config/`` du package.

    Returns:
        :class:`PgnFilter` prêt à l'emploi.

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
        >>> f = load_pgn_filter_from_config(tmp)
        >>> f.player_name
        'Dupont'
        >>> f.results
        ['1-0']
        >>> tmp.unlink()
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "player_config.yaml"

    if not config_path.exists():
        return PgnFilter()

    with config_path.open(encoding="utf-8") as fh:
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
