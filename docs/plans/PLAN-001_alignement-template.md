---
type: Plan
id: PLAN-001
title: "Réalignement de chess_coach sur project_template"
description: "Mode opératoire en 11 phases pour aligner l'outillage, la config, la documentation et CLAUDE.md sur project_template."
status: draft
implements: SPEC-001
tags: [python, tooling]
timestamp: 2026-08-23
perimeter: project
audience: []
---

# Réalignement de chess_coach sur project_template

## Périmètre

Ce plan implémente SPEC-001 : rattacher `chess_coach` à `project_template`,
réaligner l'outillage et la configuration, restructurer `docs/`, reconstituer
le contexte `.claude/`, corriger les deux bugs de code identifiés en
diagnostic, et couvrir le projet d'une première vague de tests — sans
changer le comportement fonctionnel du programme.

Chaque phase ci-dessous fait l'objet d'un commit atomique distinct et est
validée avant de passer à la suivante.

## Étapes

### 1. Rattachement au template

- Fichiers cibles : `.cruft.json`
- Action : créer/lier `.cruft.json` vers
  `https://github.com/mattdav/project_template` au commit courant du
  template ; préférer `cruft link` à un fichier écrit à la main si possible.
- Vérification : `cruft check` s'exécute et le résultat est explicité.

### 2. Fichiers de configuration et outillage manquants

- Fichiers cibles : `.pre-commit-config.yaml`, `.markdownlint.jsonc`,
  `.prettierrc`, `.prettierignore`, `.gitattributes`, `CHANGELOG.md`,
  `CONTRIBUTING.md`, `index.md`, `log.md`
- Action : créer ces fichiers en résolvant les gabarits Jinja du template
  (`project_name=chess_coach`, etc.) ; basculer la section « Changelog »
  du `README.md` vers `CHANGELOG.md`.
- Vérification : chaque fichier existe et ne contient plus de syntaxe
  Jinja non résolue.

### 3. `pyproject.toml`

- Fichiers cibles : `pyproject.toml`
- Action : migrer les outils de dev vers `[dependency-groups]`, ajouter
  `[tool.commitizen]`, `line-ending = "lf"`, `--ignore=src/chess_coach/config`
  dans `addopts`, et une valeur atteignable pour `[tool.coverage.report]
  fail_under` (à proposer avant application, cf. consigne du chantier) — en
  préservant les dépendances runtime réelles (`anthropic`, `beartype`,
  `httpx`, `pandas`, `pyarrow`, `python-chess`, `python-dotenv`, `pyyaml`,
  extra `podcast`).
- Vérification : `uv sync` réussit.

### 4. `tasks.py`

- Fichiers cibles : `tasks.py`
- Action : remplacer par la version du template (`clean`, `lint`,
  `precommit_install`, `test`, `docs`, `build`, `release`), sans tâche
  `wiki_check`.
- Vérification : `uv run inv --list` affiche les tâches attendues.

### 5. Arborescence `docs/`

- Fichiers cibles : `docs/source/` → `docs/code/`, `docs/specs/`,
  `docs/fixes/`, `docs/_templates/`, `docs/index.md`
- Action : migrer Sphinx vers `docs/code/`, créer `docs/fixes/` (pas
  `fixs/`), copier les gabarits `spec.md`/`fix.md`/`plan.md`.
- Vérification : `uv run inv docs` build sans erreur.

### 6. Contexte Claude (`.claude/`)

- Fichiers cibles : `.claude/rules/`, `.claude/commands/doc-new.md`,
  `.claude/settings.json`, `.claude/DECISIONS-archive.md`,
  `.claude/DECISIONS.md`, `.claude/LESSONS.md`
- Action : ajouter les fichiers manquants ; reconstituer `DECISIONS.md`
  depuis le git log/README/code (suppression Lichess, suppression caissAI
  runtime, `main.py` → `bin/session.py`, agrégation par ECO, FEN
  pré-coup, modèles LLM pilotés par `.env`) — signaler ce qui reste
  incertain plutôt que de l'inventer.
- Vérification : relecture manuelle, aucune décision non vérifiable.

### 7. `okf-base.yaml`

- Fichiers cibles : `okf-base.yaml`
- Action : ajouter les types `Command`, `Spec`, `Fix`, `Plan`, retirer
  `type` des champs `required`, retirer les `status_values: false`
  explicites.
- Vérification : les documents OKF déjà créés (SPEC-001, PLAN-001)
  valident contre ce profil.

### 8. CI GitHub

- Fichiers cibles : `.github/workflows/ci.yml` (remplace `lint.yml`),
  `.github/workflows/docs.yml`
- Action : `ci.yml` du template (lint pre-commit + tests + commitizen) ;
  adapter `docs.yml` au chemin `docs/code/`.
- Vérification : lecture du YAML, cohérence des chemins.

### 9. `CLAUDE.md` et corrections de code

- Fichiers cibles : `CLAUDE.md`, `src/chess_coach/__main__.py`,
  `src/chess_coach/bin/py.typed`
- Action : réécrire `CLAUDE.md` entièrement depuis le code réel (structure
  du CLAUDE.md du template) ; supprimer le doublon `bin/py.typed` ;
  remplacer `importlib.resources.path(..., "")` par
  `Path(__file__).parent / folder_name` dans `_get_package_dir`.
- Vérification : `chess_coach --pgn <pgn> --list` fonctionne toujours ;
  `CLAUDE.md` ne mentionne plus Lichess collector / caissAI runtime /
  `main.py` / clés obligatoires supprimées.

### 10. Tests

- Fichiers cibles : `tests/`, `tests/unit/`, `tests/conftest.py`
- Action : créer une première vague de tests unitaires sur
  `pgn_collector.parse_game_indices`, `pgn_collector.select_games`,
  `pattern_detector.build_weakness_profile`,
  `podcast_generator.extract_podcast_topics`/`_format_topic`, mapping NAG
  de `analyzer`. Fixtures via `tmp_path`, nommage
  `test_<fonction>_<scenario>_<resultat_attendu>`.
- Vérification : `uv run inv test` passe, doctests existants toujours
  verts.

### 11. Validation finale

- Fichiers cibles : (aucun — validation globale)
- Action : `uv sync`, `uv run inv precommit-install`, `uv run inv lint`,
  `uv run inv test`, `uv run inv docs`, puis `uv run pre-commit run
  --all-files` deux fois de suite (idempotence).
- Vérification : tout passe ; second passage pre-commit sans modification ;
  `chess_coach --pgn <pgn> --list` et `--games 250:266 --dry-run`
  fonctionnent comme avant le chantier.

## Mise à jour documentaire

- [ ] `README.md` mis à jour si le fonctionnement change (a priori non,
      sauf retrait de la section Changelog déplacée vers `CHANGELOG.md`)
- [ ] Statut de `SPEC-001` passé à `implemented`
- [ ] `.claude/progress.log` complété en fin de chantier (résumé du
      chantier)
- [ ] `.claude/DECISIONS.md` et `.claude/LESSONS.md` complétés avec les
      décisions structurantes et pièges rencontrés pendant le chantier

## Vérification finale

```bash
uv sync
uv run inv precommit-install
uv run inv lint      # doit passer à zéro
uv run inv test      # doit passer
uv run inv docs       # build Sphinx sans erreur

uv run pre-commit run --all-files   # deux fois de suite, idempotent

uv run chess_coach --pgn "<un PGN annoté existant>" --list
uv run chess_coach --pgn "<un PGN annoté existant>" --games 250:266 --dry-run
```
