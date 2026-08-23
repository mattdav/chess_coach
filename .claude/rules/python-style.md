---
type: ProjectStandards
project: chess_coach
updated: 2026-08-23
tags: [python]
---

# Style Python

Règles observables dans ce projet (`pyproject.toml`, `.pre-commit-config.yaml`,
`CONTRIBUTING.md`) — à respecter pour tout code écrit ou modifié sous `src/`.

## Structure du package

```text
src/chess_coach/
├── bin/        ← scripts exécutables et points d'entrée CLI
├── config/     ← classe Settings (pydantic-settings) et fichiers yaml
├── data/       ← accès, chargement et transformation des données
├── log/        ← configuration du logging
├── __init__.py
└── __main__.py ← point d'entrée principal
```

Ne pas mélanger logique métier et configuration dans le même fichier.

## Qualité

- Type hints obligatoires sur toutes les fonctions et méthodes publiques.
- Docstrings au format Google sur toutes les fonctions et méthodes publiques.
- Aucun `# noqa` ni `# type: ignore` sans commentaire justificatif sur la
  même ligne.
- Éviter `Any` sauf cas justifié.

## Configuration et secrets

- Aucune valeur hardcodée (URL, clé, timeout, chemin absolu) dans le code.
- Secrets et valeurs locales → `.env` (jamais commité).
- Configuration structurée → `config/settings.yaml`.
- Valeurs par défaut non sensibles → `config/settings.default.yaml` (commité).
- Toute nouvelle variable d'environnement est ajoutée à `.env.example` avec
  une description en commentaire.

## Lint

`uv run inv lint` délègue entièrement à `pre-commit run --all-files` (source
unique de vérité, voir `tasks.py` et `.pre-commit-config.yaml`) :

- `ruff check --fix` puis `ruff format` sur `src/`, `tests/`, `tasks.py`
  (line-length 88, quotes doubles, indentation 4 espaces).
- `mypy` en mode strict sur `src/`, `tests/`, `tasks.py`.
- `markdownlint-cli2` et `prettier` sur les fichiers Markdown/YAML/JSON.

Cette commande doit passer à zéro avant tout commit.

## Tests

- Un fichier de test par module : `tests/unit/test_<module>.py`.
- Fixtures partagées dans `tests/conftest.py`.
- Nommage explicite : `test_<fonction>_<scenario>_<resultat_attendu>`.
