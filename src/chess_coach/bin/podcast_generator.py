"""Génération de podcasts pédagogiques depuis le plan d'entraînement.

Utilise podgenai (``from podgenai import generate_media``) pour produire
un MP3 d'environ une heure par sujet identifié dans le ``TrainingPlan``.

Les sujets sont extraits automatiquement du plan Claude : ``week_theme``
et ``key_concepts`` constituent les topics envoyés à podgenai, enrichis
d'un préfixe contextuel pour focaliser le contenu sur les échecs.

Prérequis :
    - ``OPENAI_API_KEY`` dans l'environnement (podgenai utilise OpenAI TTS)
    - ``ffmpeg`` accessible dans le PATH
    - ``pip install podgenai``
"""

import logging
import os
from pathlib import Path
from typing import Any

from chess_coach.bin.coach import TrainingPlan


def _format_topic(raw_topic: str, elo: int) -> str:
    """Formate un sujet brut en topic podgenai contextualisé aux échecs.

    Args:
        raw_topic: Sujet extrait du plan (ex: ``"Les finales de tours"``).
        elo: Elo du joueur pour contextualiser le niveau.

    Returns:
        Topic formaté pour podgenai.

    Examples:
        >>> t = _format_topic("Les finales de tours", 1500)
        >>> "échecs" in t.lower()
        True
    """
    return (
        f"Aux échecs, {raw_topic.lower().rstrip('.')} "
        f"— cours pédagogique pour un joueur de niveau {elo} Elo"
    )


def extract_podcast_topics(
    plan: TrainingPlan,
    player_elo: int,
    max_topics: int = 3,
) -> list[str]:
    """Extrait les sujets pédagogiques prioritaires du plan d'entraînement.

    Sélectionne dans l'ordre : le thème de la semaine, puis les concepts clés
    jusqu'à ``max_topics`` sujets au total.

    Args:
        plan: Plan d'entraînement généré par Claude.
        player_elo: Elo du joueur (pour contextualiser les topics podgenai).
        max_topics: Nombre maximum de podcasts à générer (défaut : 3).

    Returns:
        Liste de topics formatés prêts pour podgenai.

    Examples:
        >>> from chess_coach.bin.coach import TrainingPlan
        >>> plan: TrainingPlan = {
        ...     "week_theme": "Finales de tours",
        ...     "daily_tasks": [],
        ...     "key_concepts": ["Opposition", "Zugzwang", "Rook endings"],
        ...     "success_metrics": "70% de réussite",
        ... }
        >>> topics = extract_podcast_topics(plan, player_elo=1500, max_topics=2)
        >>> len(topics)
        2
        >>> "finales de tours" in topics[0].lower()
        True
    """
    candidates: list[str] = []

    week_theme = plan.get("week_theme", "").strip()
    if week_theme:
        candidates.append(_format_topic(week_theme, player_elo))

    for concept in plan.get("key_concepts", []):
        if concept.strip():
            candidates.append(_format_topic(concept.strip(), player_elo))

    return candidates[:max_topics]


def generate_podcasts(
    plan: TrainingPlan,
    player_elo: int,
    output_dir: Path,
    max_topics: int = 3,
    max_sections: int | None = None,
) -> list[Path]:
    """Génère des podcasts MP3 depuis les sujets du plan d'entraînement.

    Appelle ``podgenai.generate_media`` pour chaque sujet. Les fichiers MP3
    sont écrits dans ``output_dir`` avec un nom auto-déterminé par podgenai.

    Args:
        plan: Plan d'entraînement généré par Claude.
        player_elo: Elo du joueur (pour contextualiser les topics).
        output_dir: Dossier de sortie pour les MP3 (doit exister).
        max_topics: Nombre maximum de podcasts à générer (défaut : 3).
        max_sections: Nombre maximum de sections podgenai par podcast.
            None = pas de limite (durée ~1h). Valeur entre 3 et 100.

    Returns:
        Liste des chemins MP3 générés avec succès.

    Raises:
        ImportError: Si podgenai n'est pas installé.
        RuntimeError: Si ``OPENAI_API_KEY`` est absent de l'environnement.

    Examples:
        >>> callable(generate_podcasts)
        True
    """
    try:
        from podgenai import generate_media
    except ImportError as exc:
        raise ImportError(
            "podgenai n'est pas installé. Lancer : uv pip install podgenai"
        ) from exc

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY absent de l'environnement. "
            "Requis par podgenai pour la génération TTS."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    topics = extract_podcast_topics(plan, player_elo, max_topics)

    if not topics:
        logging.warning("generate_podcasts : aucun sujet extrait du plan.")
        return []

    generated: list[Path] = []
    for i, topic in enumerate(topics, 1):
        print(f"  Podcast {i}/{len(topics)} : {topic[:70]}...")
        try:
            kwargs: dict[str, Any] = {"output_path": output_dir}
            if max_sections is not None:
                kwargs["max_sections"] = max_sections

            result = generate_media(topic, **kwargs)
            if result is None:
                logging.warning(
                    "generate_podcasts : génération échouée pour '%s'", topic
                )
                print("    ✗ Échec (podgenai a retourné None)")
            else:
                mp3_path = Path(result)
                generated.append(mp3_path)
                print(f"    ✓ {mp3_path.name}")
                logging.info("generate_podcasts : podcast généré → %s", mp3_path)
        except Exception as exc:
            logging.error("generate_podcasts : erreur pour '%s' : %s", topic, exc)
            print(f"    ✗ Erreur : {exc}")

    print(f"\n  {len(generated)}/{len(topics)} podcast(s) générés dans {output_dir}")
    return generated
