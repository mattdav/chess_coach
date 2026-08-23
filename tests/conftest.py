"""Fixtures partagées par la suite de tests."""

import pytest

_PATH_ENV_VARS = (
    "CHESS_COACH_DATA_DIR",
    "CHESS_COACH_PLANS_DIR",
    "CHESS_COACH_PODCAST_DIR",
    "CHESS_COACH_LOG_DIR",
    "CHESS_COACH_CONFIG",
)


@pytest.fixture(autouse=True)
def clean_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise les variables de chemin héritées de l'environnement.

    Sans cela, un poste de développement où ces variables sont définies
    (via ``.env`` chargé dans le shell, ou l'environnement système) ferait
    passer ou échouer les tests selon la machine — exactement le type de
    dépendance à l'environnement local que la CI finit par révéler.
    """
    for var in _PATH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
