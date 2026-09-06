"""Génération du plan d'entraînement hebdomadaire via l'API Claude."""

import json
import logging
import os
from dataclasses import asdict
from typing import Any, TypedDict

import anthropic
from anthropic.types import Message, TextBlock

from chess_coach.bin.gm_games import OpeningStudy
from chess_coach.bin.pattern_detector import WeaknessProfile

_COACH_SYSTEM = """Tu es un coach d'échecs expert.
Tu reçois le profil de faiblesses d'un joueur, annoté par le moteur caissAI
(Maia2 + Stockfish), et tu génères un plan d'entraînement hebdomadaire précis,
actionnable et progressif.
Réponds UNIQUEMENT en JSON valide selon le schéma fourni, sans markdown,
sans commentaires."""

# Modèle Claude par défaut, surchargeable via ANTHROPIC_MODEL dans .env.
_DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# Budget de génération. Doit couvrir le JSON du plan (~2000 tokens) ET le
# raisonnement interne : les modèles récents émettent des blocs `thinking`
# par défaut, qui se prélèvent sur ce même budget. Avec 4096, le budget
# pouvait être épuisé avant le premier bloc texte.
_MAX_TOKENS = 16000

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Retourne le client Anthropic (singleton lazy)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


class DailyExercise(TypedDict):
    """Exercice individuel dans une journée d'entraînement.

    Examples:
        >>> ex: DailyExercise = {
        ...     "type": "puzzles",
        ...     "description": "Tactiques sur le thème de la fourchette",
        ...     "duration_min": 20,
        ...     "lichess_url": "https://lichess.org/training/fork",
        ... }
        >>> ex["type"]
        'puzzles'
    """

    type: str  # "puzzles" | "game_analysis" | "opening_study" | "endgame"
    description: str
    duration_min: int
    lichess_url: str


class DailyTask(TypedDict):
    """Programme d'une journée d'entraînement.

    Examples:
        >>> task: DailyTask = {
        ...     "day": "Lundi",
        ...     "focus": "Tactiques",
        ...     "exercises": [],
        ... }
        >>> task["day"]
        'Lundi'
    """

    day: str
    focus: str
    exercises: list[DailyExercise]


class TrainingPlan(TypedDict):
    """Plan d'entraînement hebdomadaire généré par Claude.

    Examples:
        >>> plan: TrainingPlan = {
        ...     "week_theme": "Maîtriser les finales de tours",
        ...     "daily_tasks": [],
        ...     "key_concepts": ["Opposition", "Zugzwang"],
        ...     "success_metrics": "Taux de réussite puzzles > 70%",
        ... }
        >>> plan["week_theme"]
        'Maîtriser les finales de tours'
    """

    week_theme: str
    daily_tasks: list[DailyTask]
    key_concepts: list[str]
    success_metrics: str


_PLAN_SCHEMA = {
    "week_theme": "string — thème principal de la semaine",
    "daily_tasks": [
        {
            "day": "Lundi",
            "focus": "string — objectif de la journée",
            "exercises": [
                {
                    "type": "puzzles|game_analysis|opening_study|endgame",
                    "description": "string — description précise de l'exercice",
                    "duration_min": 20,
                    "lichess_url": "URL Lichess ou chaîne vide",
                }
            ],
        }
    ],
    "key_concepts": ["concept 1", "concept 2", "concept 3"],
    "success_metrics": "string — comment mesurer les progrès en fin de semaine",
}


def _serialize_profile(profile: WeaknessProfile) -> dict[str, Any]:
    """Sérialise le profil pour l'envoi à Claude.

    Convertit les dataclasses ``MoveError`` en dicts JSON-compatibles et
    enrichit chaque position avec le commentaire caissAI pour que Claude
    dispose du contexte pédagogique complet.

    Args:
        profile: Profil de faiblesses.

    Returns:
        Dict JSON-serializable.

    Examples:
        >>> from chess_coach.bin.pattern_detector import WeaknessProfile
        >>> p: WeaknessProfile = {
        ...     "total_games": 0, "avg_acpl": 0.0, "weakest_phase": "middlegame",
        ...     "phase_breakdown": {}, "category_breakdown": {},
        ...     "problematic_openings": [],
        ...     "avg_cp_loss_by_phase": {}, "worst_positions": [],
        ...     "annotated_pgns": [],
        ... }
        >>> d = _serialize_profile(p)
        >>> "worst_positions" in d
        True
    """
    serializable: dict[str, Any] = dict(profile)
    serializable["worst_positions"] = [
        {
            **asdict(err),
            # Le commentaire caissAI est déjà dans err.comment — on le met
            # en évidence pour que Claude le lise en premier.
            "caissai_comment": err.comment,
        }
        for err in profile["worst_positions"]
    ]
    # Les PGN annotés complets ne sont pas envoyés à Claude (trop longs),
    # on envoie uniquement les stats agrégées et les pires positions.
    serializable.pop("annotated_pgns", None)
    return serializable


def _extract_text(response: Message) -> str:
    """Concatène les blocs texte d'une réponse Claude.

    La réponse peut contenir d'autres types de blocs (``thinking``,
    ``redacted_thinking``, ``tool_use``) qui précèdent le texte : on ne peut
    donc pas se contenter de ``response.content[0]``.

    Args:
        response: Réponse brute de l'API Messages.

    Returns:
        Le texte concaténé, débarrassé des espaces de bord.
    """
    return "\n".join(
        block.text for block in response.content if isinstance(block, TextBlock)
    ).strip()


def _strip_code_fence(raw: str) -> str:
    """Retire un éventuel encadrement en bloc de code Markdown autour du JSON.

    Args:
        raw: Texte brut renvoyé par Claude.

    Returns:
        Le contenu sans les délimiteurs de bloc de code.

    Examples:
        >>> _strip_code_fence('```json\\n{"a": 1}\\n```')
        '{"a": 1}'
        >>> _strip_code_fence('{"a": 1}')
        '{"a": 1}'
    """
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    # Retire la ligne d'ouverture puis la clôture finale.
    stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
    return stripped.rstrip("`").rstrip()


def generate_weekly_plan(
    profile: WeaknessProfile,
    player_elo: int,
    max_daily_minutes: int = 45,
    model: str = _DEFAULT_MODEL,
    gm_studies: list[OpeningStudy] | None = None,
) -> TrainingPlan:
    """Génère un plan d'entraînement hebdomadaire personnalisé via Claude.

    Le prompt envoie à Claude :
    - Les statistiques agrégées (ACPL, phase faible, ventilation erreurs)
    - Les 10 pires positions avec leur commentaire caissAI
    - Les études de parties de GM pour les ouvertures problématiques

    Args:
        profile: Profil de faiblesses construit par ``pattern_detector``.
        player_elo: Elo courant du joueur (pour calibrer la difficulté).
        max_daily_minutes: Durée maximale d'entraînement par jour.
        model: Modèle Claude à utiliser. Défaut : ANTHROPIC_MODEL dans .env,
            sinon "claude-sonnet-4-5".
        gm_studies: Études de parties de GM récupérées depuis la Masters API
            Lichess. Si fourni, enrich le prompt avec les exemples de GM.

    Returns:
        Plan d'entraînement structuré sur 7 jours.

    Raises:
        anthropic.APIError: En cas d'erreur API Claude.
        ValueError: Si la réponse est tronquée (``max_tokens``) ou ne
            contient aucun bloc texte.
        json.JSONDecodeError: Si Claude retourne du JSON invalide.

    Examples:
        >>> isinstance(_PLAN_SCHEMA, dict)
        True
    """
    profile_payload = _serialize_profile(profile)

    # Section parties de GM
    gm_section = ""
    if gm_studies:
        gm_lines = [
            "\nParties de grands maîtres sur tes ouvertures problématiques "
            "(source : Lichess Masters Database) :\n"
        ]
        for study in gm_studies:
            gm_lines.append(study.summary())
            gm_lines.append(
                f"  Lien d'étude : https://lichess.org/opening/{study.eco}\n"
            )
        gm_section = "\n".join(gm_lines)

    prompt = (
        f"Profil du joueur (Elo {player_elo}) annoté par caissAI"
        f" (Maia2 + Stockfish) :\n"
        f"{json.dumps(profile_payload, indent=2, ensure_ascii=False)}\n\n"
        "Notes sur les données :\n"
        "- 'category' : 'blunder' ($4), 'mistake' ($2), 'dubious' ($5) "
        "selon la classification caissAI\n"
        "- 'caissai_comment' : commentaire pédagogique de caissAI sur chaque "
        "erreur (espérance de gain perdue)\n"
        "- 'avg_cp_loss_by_phase' : perte proxy par phase "
        "(blunder=300, mistake=150, dubious=75 centipawns)\n"
        f"{gm_section}\n"
        f"Génère un plan d'entraînement pour la semaine prochaine.\n"
        f"Schéma JSON attendu :\n"
        f"{json.dumps(_PLAN_SCHEMA, indent=2, ensure_ascii=False)}\n\n"
        f"Règles :\n"
        f"- Maximum {max_daily_minutes} min/jour\n"
        f"- Priorise la phase la plus faible : {profile['weakest_phase']}\n"
        f"- Tiens compte des commentaires caissAI pour cibler les thèmes "
        f"tactiques spécifiques\n"
        f"- Pour les ouvertures problématiques, référence les parties de GM "
        f"ci-dessus et propose d'étudier leurs lignes clés sur Lichess\n"
        f"- Adapte la difficulté des puzzles à l'Elo : {player_elo}\n"
        f"- Les URLs Lichess doivent être réelles et accessibles\n"
        f"- Retourne uniquement le JSON, rien d'autre."
    )

    response = _get_client().messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=_COACH_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    logging.debug(
        "generate_weekly_plan : modèle=%s stop_reason=%s blocs=%s usage=%s",
        model,
        response.stop_reason,
        [block.type for block in response.content],
        response.usage,
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"Réponse Claude tronquée (max_tokens={_MAX_TOKENS} atteint, "
            f"{response.usage.output_tokens} tokens produits) — augmenter "
            "_MAX_TOKENS dans coach.py."
        )

    raw = _extract_text(response)
    if not raw:
        raise ValueError(
            "Réponse Claude inattendue : pas de bloc texte "
            f"(modèle={model}, stop_reason={response.stop_reason}, "
            f"blocs={[block.type for block in response.content]})."
        )

    plan: TrainingPlan = json.loads(_strip_code_fence(raw))
    logging.info("generate_weekly_plan : thème '%s'", plan.get("week_theme", "?"))
    return plan
