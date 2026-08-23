"""Résolution des chemins runtime de chess_coach.

Le programme n'écrit jamais dans le package installé : une réinstallation
ou un ``uv tool upgrade`` remplacerait le contenu du package et effacerait
la base SQLite, les plans générés et la configuration joueur.

Tous les emplacements suivent la même précédence :
``argument CLI > variable d'environnement > défaut utilisateur``.

Variables reconnues :
    CHESS_COACH_DATA_DIR      Base SQLite et dossier d'état par défaut
    CHESS_COACH_PLANS_DIR     Plans d'entraînement Markdown
    CHESS_COACH_PODCAST_DIR   MP3 générés par podgenai
    CHESS_COACH_LOG_DIR       Journal applicatif
    CHESS_COACH_CONFIG        Fichier player_config.yaml
"""

import logging
import os
import shutil
from pathlib import Path

CONFIG_FILENAME = "player_config.yaml"


def default_state_dir() -> Path:
    """Dossier d'état par défaut, situé hors du package installé.

    Returns:
        ``%LOCALAPPDATA%/chess_coach`` sous Windows,
        ``~/.local/share/chess_coach`` ailleurs.

    Examples:
        >>> default_state_dir().name
        'chess_coach'
    """
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        return Path(local_appdata) / "chess_coach"
    return Path.home() / ".local" / "share" / "chess_coach"


def resolve_dir(cli_value: str | None, env_var: str, default: Path) -> Path:
    """Résout un dossier selon la précédence CLI > environnement > défaut.

    Args:
        cli_value: Valeur passée en argument CLI (prioritaire), ou None.
        env_var: Nom de la variable d'environnement à consulter ensuite.
        default: Valeur de repli si ni l'un ni l'autre n'est renseigné.

    Returns:
        Chemin résolu, avec ``~`` développé.

    Examples:
        >>> resolve_dir("/tmp/cli", "UNSET_VAR_XYZ", Path("/tmp/def")).name
        'cli'
        >>> resolve_dir(None, "UNSET_VAR_XYZ", Path("/tmp/def")).name
        'def'
        >>> resolve_dir("", "UNSET_VAR_XYZ", Path("/tmp/def")).name
        'def'
    """
    if cli_value:
        return Path(cli_value).expanduser()
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return Path(env_value).expanduser()
    return default


def packaged_config_path() -> Path:
    """Chemin du ``player_config.yaml`` livré avec le package.

    Sert uniquement de modèle initial : ce fichier n'est jamais modifié à
    l'exécution, puisqu'il serait écrasé à la prochaine mise à jour.

    Returns:
        Chemin vers le YAML packagé (peut ne pas exister).

    Examples:
        >>> packaged_config_path().name
        'player_config.yaml'
    """
    return Path(__file__).parent.parent / "config" / CONFIG_FILENAME


def resolve_config_path() -> Path:
    """Résout l'emplacement du ``player_config.yaml`` utilisateur.

    Précédence :

    1. ``CHESS_COACH_CONFIG`` — chemin complet du fichier
    2. ``CHESS_COACH_DATA_DIR/player_config.yaml``
    3. ``default_state_dir()/player_config.yaml``

    Piloté par environnement uniquement, sans argument CLI : la
    configuration est lue avant le parsing des arguments, puisqu'elle
    alimente les valeurs par défaut de ``--player`` et ``--elo``.

    Returns:
        Chemin du fichier de configuration utilisateur (peut ne pas
        encore exister ; voir :func:`ensure_user_config`).

    Examples:
        >>> resolve_config_path().name
        'player_config.yaml'
    """
    explicit = os.environ.get("CHESS_COACH_CONFIG", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    state_dir = resolve_dir(None, "CHESS_COACH_DATA_DIR", default_state_dir())
    return state_dir / CONFIG_FILENAME


def ensure_user_config() -> Path:
    """Garantit qu'un ``player_config.yaml`` utilisateur existe.

    Au premier lancement, copie le modèle packagé vers l'emplacement
    utilisateur résolu. Un fichier déjà présent n'est jamais écrasé : les
    valeurs saisies par l'utilisateur priment toujours sur le modèle.

    Returns:
        Chemin du fichier de configuration utilisateur. Si la copie
        échoue (droits, disque), retourne le chemin packagé en repli pour
        que le programme reste utilisable en lecture seule.

    Note:
        Fonction à effet de bord (écriture disque) : elle est couverte par
        ``tests/unit/test_paths.py`` sur un dossier temporaire, pas par un
        doctest qui écrirait dans la configuration réelle de l'utilisateur.
    """
    target = resolve_config_path()
    if target.exists():
        return target

    source = packaged_config_path()
    if not source.exists():
        logging.warning("ensure_user_config : modèle packagé introuvable (%s).", source)
        return target

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except OSError as exc:
        logging.error(
            "ensure_user_config : copie impossible vers %s (%s) — "
            "lecture du modèle packagé.",
            target,
            exc,
        )
        return source

    logging.info("ensure_user_config : configuration initialisée → %s", target)
    print(f"    Configuration joueur initialisée : {target}")
    return target
