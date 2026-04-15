"""Extraction des erreurs depuis des parties déjà annotées par caissAI.

Ce module lit directement le PGN annoté produit par caissAI (NAGs, commentaires,
variantes) et en extrait un GameReport structuré. Il ne lance aucune analyse :
caissAI doit avoir été exécuté en amont.

Mapping NAG → MoveError
-----------------------
    NAG_BLUNDER ($4)       → catégorie "blunder"  proxy cp_loss = 300
    NAG_MISTAKE ($2)       → catégorie "mistake"  proxy cp_loss = 150
    NAG_DUBIOUS_MOVE ($5)  → catégorie "dubious"  proxy cp_loss = 75
    Autres NAGs            → ignorés (bons coups, coups forcés…)
"""

import logging
from dataclasses import dataclass, field

import chess
import chess.pgn

# NAGs caissAI qui indiquent une erreur du joueur
_ERROR_NAGS: frozenset[int] = frozenset(
    [
        chess.pgn.NAG_DUBIOUS_MOVE,  # $5 — coup douteux
        chess.pgn.NAG_MISTAKE,  # $2 — erreur
        chess.pgn.NAG_BLUNDER,  # $4 — gaffe
    ]
)

_NAG_CATEGORY: dict[int, str] = {
    chess.pgn.NAG_DUBIOUS_MOVE: "dubious",
    chess.pgn.NAG_MISTAKE: "mistake",
    chess.pgn.NAG_BLUNDER: "blunder",
}

_NAG_CP_PROXY: dict[int, int] = {
    chess.pgn.NAG_DUBIOUS_MOVE: 75,
    chess.pgn.NAG_MISTAKE: 150,
    chess.pgn.NAG_BLUNDER: 300,
}


@dataclass
class MoveError:
    """Erreur détectée sur un coup dans un PGN annoté par caissAI.

    Examples:
        >>> err = MoveError(
        ...     fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        ...     played="e7e5",
        ...     best="c7c5",
        ...     cp_loss=150,
        ...     category="mistake",
        ...     phase="opening",
        ...     move_number=1,
        ...     comment="Espérance de gain pour les noirs : -12.50%.",
        ... )
        >>> err.category
        'mistake'
    """

    fen: str
    played: str  # notation UCI
    best: str  # meilleur coup UCI (variante caissAI)
    cp_loss: int  # proxy centipawns basé sur le NAG
    category: str  # "dubious" | "mistake" | "blunder"
    phase: str  # "opening" | "middlegame" | "endgame"
    move_number: int
    comment: str = ""  # commentaire caissAI sur le coup


@dataclass
class GameReport:
    """Rapport d'analyse d'une partie annotée par caissAI.

    Examples:
        >>> report = GameReport(game_id="abc", opening="Sicilian Defense")
        >>> report.acpl
        0.0
        >>> report.annotated_pgn
        ''
        >>> report.eco
        ''
    """

    game_id: str
    opening: str
    eco: str = ""  # code ECO (ex: "B30") — toujours présent dans caissAI
    errors: list[MoveError] = field(default_factory=list)
    acpl: float = 0.0  # moyenne des cp_loss proxy sur les erreurs
    annotated_pgn: str = ""  # PGN annoté complet (texte brut)


def report_from_pgn(
    annotated_game: chess.pgn.Game,
    player_name: str = "",
) -> GameReport:
    """Extrait un GameReport depuis une partie déjà annotée par caissAI.

    Parcourt les nœuds de la ligne principale. Pour chaque nœud portant
    un NAG d'erreur ($2, $4, $5), crée un MoveError. Ne relance aucune
    analyse : le PGN doit contenir les annotations caissAI.

    Args:
        annotated_game: Partie PGN annotée par caissAI.
        player_name: Si fourni, ne remonte que les erreurs du joueur dont
            le nom correspond (correspondance partielle, insensible à la casse)
            dans les headers White ou Black.

    Returns:
        Rapport structuré avec la liste des erreurs et l'ACPL proxy.

    Examples:
        >>> import chess.pgn
        >>> game = chess.pgn.Game()
        >>> game.headers["Site"] = "test"
        >>> game.headers["Opening"] = "King's Pawn"
        >>> report = report_from_pgn(game)
        >>> report.game_id
        'test'
        >>> report.acpl
        0.0
    """
    headers = annotated_game.headers
    report = GameReport(
        game_id=headers.get("Site", headers.get("Event", "")),
        opening=headers.get("Opening", "Unknown"),
        eco=headers.get("ECO", ""),
        annotated_pgn=str(annotated_game),
    )

    # Déterminer la couleur du joueur suivi (None = les deux camps)
    player_color: chess.Color | None = None
    if player_name:
        white = headers.get("White", "").lower()
        black = headers.get("Black", "").lower()
        name = player_name.lower()
        if name in white:
            player_color = chess.WHITE
        elif name in black:
            player_color = chess.BLACK

    cp_losses: list[int] = []

    for node in annotated_game.mainline():
        # Filtrer sur le joueur si demandé
        if player_color is not None and node.parent is not None:
            if node.parent.board().turn != player_color:
                continue

        error_nag = next((nag for nag in node.nags if nag in _ERROR_NAGS), None)
        if error_nag is None:
            continue

        cp_proxy = _NAG_CP_PROXY[error_nag]
        cp_losses.append(cp_proxy)
        # FEN avant le coup joué — permet de reproduire la position sur l'échiquier
        parent_board = node.parent.board() if node.parent else node.board()

        report.errors.append(
            MoveError(
                fen=parent_board.fen(),
                played=node.move.uci() if node.move else "",
                best=_best_move_from_variation(node),
                cp_loss=cp_proxy,
                category=_NAG_CATEGORY[error_nag],
                phase=_get_phase(parent_board),
                move_number=parent_board.fullmove_number,
                comment=node.comment,
            )
        )

    report.acpl = round(sum(cp_losses) / len(cp_losses), 1) if cp_losses else 0.0
    logging.info(
        "report_from_pgn : %d erreurs, ACPL proxy %.1f — %s",
        len(report.errors),
        report.acpl,
        report.game_id,
    )
    return report


def _get_phase(board: chess.Board) -> str:
    """Détermine la phase de jeu à partir du plateau.

    Args:
        board: Position après le coup joué.

    Returns:
        ``"opening"`` (≤ 10 coups), ``"endgame"`` (≤ 14 pièces),
        ``"middlegame"`` sinon.

    Examples:
        >>> import chess
        >>> _get_phase(chess.Board())
        'opening'
    """
    if board.fullmove_number <= 10:
        return "opening"
    if len(board.piece_map()) <= 14:
        return "endgame"
    return "middlegame"


def _best_move_from_variation(node: chess.pgn.GameNode) -> str:
    """Extrait le meilleur coup depuis la variante caissAI du nœud parent.

    Args:
        node: Nœud courant (après le coup joué).

    Returns:
        Meilleur coup en notation UCI, ou ``""`` si indisponible.

    Examples:
        >>> import chess.pgn
        >>> game = chess.pgn.Game()
        >>> node = game.add_variation(chess.Move.from_uci("e2e4"))
        >>> _best_move_from_variation(node)
        ''
    """
    parent = node.parent
    if parent is None:
        return ""
    for variation in parent.variations:
        if not variation.is_main_variation():
            move = variation.move
            return move.uci() if move is not None else ""
    return ""
