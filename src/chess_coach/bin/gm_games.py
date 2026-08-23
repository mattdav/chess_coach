"""Récupération de parties de grands maîtres via la Lichess Opening Explorer API.

Endpoint : https://explorer.lichess.ovh/masters
(Si hors service, fallback sur https://explorer.lichess.ovh/lichess
avec ratings=2200,2500)

Stratégie FEN :
    Au lieu de naviguer coup par coup pour atteindre un ECO, on lit directement
    l'EPD correspondant depuis lichess_eco.parquet (déjà présent dans caissAI).
    L'EPD est converti en FEN complet et passé directement à l'API.
    Cela élimine la navigation et garantit d'atteindre la bonne position.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

_MASTERS_API = "https://explorer.lichess.ovh/masters"
_LICHESS_API = "https://explorer.lichess.ovh/lichess"
_EXPORT_API = "https://lichess.org/game/export"

# Délai poli entre les requêtes API
_DELAY_S = 0.5

# Cache du parquet ECO {eco -> epd}
_eco_epd_cache: dict[str, str] = {}


@dataclass
class GmGameRef:
    """Référence à une partie de grand maître.

    Examples:
        >>> ref = GmGameRef(
        ...     game_id="abc123",
        ...     white="Carlsen, Magnus",
        ...     black="Nepomniachtchi, Ian",
        ...     year=2021,
        ...     winner="white",
        ...     eco="B30",
        ...     opening_name="Sicilian Defense",
        ... )
        >>> ref.game_id
        'abc123'
    """

    game_id: str
    white: str
    black: str
    year: int
    winner: str  # "white" | "black" | "draw"
    eco: str
    opening_name: str
    pgn: str = ""  # rempli après download_pgns()


@dataclass
class OpeningStudy:
    """Ensemble de parties de GM pour étudier une ouverture problématique.

    Examples:
        >>> study = OpeningStudy(eco="B30", opening_name="Sicilian Defense")
        >>> study.eco
        'B30'
        >>> study.pgn_text
        ''
    """

    eco: str
    opening_name: str
    games: list[GmGameRef] = field(default_factory=list)

    @property
    def pgn_text(self) -> str:
        """Concatène les PGN de toutes les parties pour export disque."""
        return "\n\n".join(g.pgn for g in self.games if g.pgn)

    def summary(self) -> str:
        """Résumé court pour injection dans le prompt Claude.

        Examples:
            >>> study = OpeningStudy(eco="B30", opening_name="Sicilian Defense")
            >>> "B30" in study.summary()
            True
        """
        lines = [f"Ouverture {self.eco} — {self.opening_name}"]
        for g in self.games:
            result_str = (
                "1-0"
                if g.winner == "white"
                else "0-1"
                if g.winner == "black"
                else "1/2-1/2"
            )
            lines.append(
                f"  - {g.white} vs {g.black} ({g.year}) {result_str}"
                f"  https://lichess.org/{g.game_id}"
            )
        return "\n".join(lines)


def _epd_to_fen(epd: str) -> str:
    """Convertit un EPD en FEN complet en ajoutant les compteurs de coups.

    Args:
        epd: EPD sans les compteurs (ex: "r1bqkbnr/... w KQkq -").

    Returns:
        FEN complet avec "0 1" ajouté.

    Examples:
        >>> fen = _epd_to_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -")
        >>> fen.endswith("0 1")
        True
    """
    return f"{epd} 0 1"


def _get_fen_for_eco(eco: str, caissai_config_path: Path | None = None) -> str:
    """Récupère le FEN correspondant à un code ECO depuis lichess_eco.parquet.

    Charge le parquet une seule fois et met en cache les résultats.
    Si plusieurs lignes correspondent au même ECO, retourne la première
    (position de base de l'ouverture).

    Args:
        eco: Code ECO (ex: "B31").
        caissai_config_path: Dossier config/ de caissAI contenant
            ``lichess_eco.parquet``. Si None, cherche dans les emplacements
            standards.

    Returns:
        FEN complet, ou chaîne vide si l'ECO est introuvable.

    Examples:
        >>> _get_fen_for_eco("")
        ''
    """
    global _eco_epd_cache
    if not eco:
        return ""

    eco_upper = eco.upper()
    if eco_upper in _eco_epd_cache:
        return _eco_epd_cache[eco_upper]

    # Chercher le parquet dans les emplacements connus
    candidates: list[Path] = []
    if caissai_config_path:
        candidates.append(Path(caissai_config_path) / "lichess_eco.parquet")
    # Emplacement relatif depuis ce module (chess_coach/bin/ -> caissAI/config/)
    candidates += [
        Path(__file__).parent.parent.parent.parent.parent
        / "caissAI"
        / "src"
        / "caissAI"
        / "config"
        / "lichess_eco.parquet",
    ]

    parquet_path: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            parquet_path = candidate
            break

    if parquet_path is None:
        logging.warning("_get_fen_for_eco : lichess_eco.parquet introuvable.")
        return ""

    try:
        df = pd.read_parquet(parquet_path, columns=["eco", "epd"])
        # Peupler le cache en une seule lecture
        for _, row in df.iterrows():
            code = str(row["eco"]).upper()
            if code not in _eco_epd_cache:
                _eco_epd_cache[code] = _epd_to_fen(str(row["epd"]))
    except Exception as exc:
        logging.error("_get_fen_for_eco : erreur lecture parquet : %s", exc)
        return ""

    return _eco_epd_cache.get(eco_upper, "")


def _query_explorer(
    fen: str,
    max_games: int,
    since_year: int,
    token: str,
) -> list[GmGameRef]:
    """Interroge l'Opening Explorer Lichess pour un FEN donné.

    Tente d'abord /masters (parties FIDE 2200+), puis bascule sur
    /lichess (ratings=2200,2500) si /masters retourne une erreur.

    Args:
        fen: FEN de la position à interroger.
        max_games: Nombre max de parties à retourner.
        since_year: Filtre sur l'année des parties.
        token: Token Lichess OAuth (pour /lichess en fallback).

    Returns:
        Liste de GmGameRef sans PGN.
    """
    winner_map: dict[str | None, str] = {
        "white": "white",
        "black": "black",
        None: "draw",
    }

    def _parse_games(data: dict[str, Any], eco_hint: str = "") -> list[GmGameRef]:
        opening_info = data.get("opening") or {}
        resolved_eco = opening_info.get("eco", eco_hint) or eco_hint
        resolved_name = opening_info.get("name", resolved_eco) or resolved_eco
        refs: list[GmGameRef] = []
        for game in data.get("topGames", []):
            game_id = game.get("id", "")
            if not game_id:
                continue
            white_info = game.get("white") or {}
            black_info = game.get("black") or {}
            refs.append(
                GmGameRef(
                    game_id=game_id,
                    white=white_info.get("name", "?"),
                    black=black_info.get("name", "?"),
                    year=game.get("year", 0),
                    winner=winner_map.get(game.get("winner"), "draw"),
                    eco=resolved_eco,
                    opening_name=resolved_name,
                )
            )
        return refs

    # Tentative 1 : /masters (avec token Lichess)
    try:
        r = httpx.get(
            _MASTERS_API,
            params={"fen": fen, "topGames": max_games, "recentGames": 0},
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=10,
        )
        if r.status_code == 200:
            refs = _parse_games(r.json())
            if refs:
                logging.info("_query_explorer : %d partie(s) via /masters", len(refs))
                return refs
            logging.debug("_query_explorer : /masters OK mais 0 partie")
        else:
            logging.debug("_query_explorer : /masters HTTP %s", r.status_code)
    except Exception as exc:
        logging.debug("_query_explorer : /masters erreur : %s", exc)

    time.sleep(_DELAY_S)

    # Fallback : /lichess avec filtre ratings 2200+
    # Le paramètre `since` attend le format YYYY-MM
    since_param = f"{since_year}-01"
    if not token:
        logging.info("_query_explorer : /masters vide et pas de token pour /lichess")
        return []
    try:
        r2 = httpx.get(
            _LICHESS_API,
            params={
                "variant": "standard",
                "speeds": "classical,rapid",
                "ratings": "2200,2500",
                "fen": fen,
                "topGames": max_games,
                "recentGames": 0,
                "since": since_param,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r2.status_code == 200:
            refs2 = _parse_games(r2.json())
            logging.info(
                "_query_explorer : %d partie(s) via /lichess fallback", len(refs2)
            )
            return refs2
        logging.warning("_query_explorer : /lichess HTTP %s", r2.status_code)
    except Exception as exc:
        logging.warning("_query_explorer : /lichess erreur : %s", exc)

    return []


def fetch_master_games_for_eco(
    eco: str,
    opening_name: str,
    token: str,
    max_games: int = 5,
    since_year: int = 2000,
    caissai_config_path: Path | None = None,
) -> list[GmGameRef]:
    """Récupère les meilleures parties pour un code ECO.

    Résout le FEN depuis lichess_eco.parquet (pas de navigation API),
    puis interroge /masters et /lichess en fallback.

    Args:
        eco: Code ECO (ex: "B30").
        opening_name: Nom de l'ouverture (pour les métadonnées).
        token: Token Lichess OAuth (utilisé pour le fallback /lichess).
        max_games: Nombre max de parties (défaut : 5).
        since_year: Filtrer les parties après cette année.
        caissai_config_path: Dossier config/ de caissAI pour trouver le parquet.

    Returns:
        Liste de GmGameRef (sans PGN — appeler download_pgns ensuite).

    Examples:
        >>> fetch_master_games_for_eco("", "test", "tok", max_games=0)
        []
    """
    if not eco or max_games <= 0:
        return []

    fen = _get_fen_for_eco(eco, caissai_config_path)
    if not fen:
        logging.info("fetch_master_games_for_eco : ECO '%s' absent du parquet.", eco)
        return []

    logging.info("fetch_master_games_for_eco : ECO %s → FEN %s", eco, fen)
    refs = _query_explorer(fen, max_games, since_year, token)

    if not refs:
        print(f"      → aucune partie trouvée pour ECO {eco}")
    return refs


def download_pgns(refs: list[GmGameRef], token: str) -> list[GmGameRef]:
    """Télécharge le PGN complet de chaque partie depuis l'API Lichess.

    Args:
        refs: Références issues de fetch_master_games_for_eco.
        token: Token Lichess OAuth.

    Returns:
        La même liste avec le champ ``pgn`` rempli pour les parties
        téléchargées avec succès.

    Examples:
        >>> download_pgns([], "tok")
        []
    """
    headers = {"Authorization": f"Bearer {token}"}
    for ref in refs:
        if not ref.game_id:
            continue
        try:
            r = httpx.get(
                f"{_EXPORT_API}/{ref.game_id}",
                params={"moves": "true", "opening": "true"},
                headers={**headers, "Accept": "application/x-chess-pgn"},
                timeout=15,
            )
            if r.status_code == 200:
                ref.pgn = r.text
                logging.debug("download_pgns : %s OK", ref.game_id)
            else:
                logging.warning(
                    "download_pgns : HTTP %s pour %s", r.status_code, ref.game_id
                )
        except httpx.RequestError as exc:
            logging.warning("download_pgns : %s : %s", ref.game_id, exc)
        time.sleep(_DELAY_S)

    return refs


def fetch_opening_studies(
    problematic_openings: list[tuple[str, str, int]],
    lichess_token: str,
    caissai_config_path: Path | None = None,
    max_games_per_opening: int = 3,
    max_openings: int = 3,
    since_year: int = 2000,
) -> list[OpeningStudy]:
    """Récupère des parties de joueurs 2200+ pour les ouvertures problématiques.

    Args:
        problematic_openings: Liste de (code_ECO, nom_ouverture, nb_erreurs).
        lichess_token: Token Lichess OAuth (optionnel, utilisé pour le fallback
            /lichess si /masters est indisponible).
        caissai_config_path: Dossier config/ de caissAI contenant
            ``lichess_eco.parquet``.
        max_games_per_opening: Parties par ouverture (défaut : 3).
        max_openings: Nombre max d'ouvertures traitées (défaut : 3).
        since_year: Filtre temporel (défaut : 2000).

    Returns:
        Liste d'OpeningStudy avec leurs parties.

    Examples:
        >>> fetch_opening_studies([], "")
        []
    """
    if not problematic_openings:
        return []

    studies: list[OpeningStudy] = []
    processed = 0

    for eco, opening_name, error_count in problematic_openings:
        if processed >= max_openings:
            break
        if not eco:
            continue

        print(f"    ECO {eco} ({opening_name}) — {error_count} erreur(s)...")
        refs = fetch_master_games_for_eco(
            eco,
            opening_name,
            lichess_token,
            max_games=max_games_per_opening,
            since_year=since_year,
            caissai_config_path=caissai_config_path,
        )
        if not refs:
            continue

        refs = download_pgns(refs, lichess_token)
        studies.append(OpeningStudy(eco=eco, opening_name=opening_name, games=refs))
        processed += 1
        logging.info("fetch_opening_studies : %s — %d partie(s)", eco, len(refs))

    return studies
