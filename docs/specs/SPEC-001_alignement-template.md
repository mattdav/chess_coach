---
type: Spec
id: SPEC-001
title: "Réalignement de chess_coach sur project_template"
description: "Remettre l'outillage, la config et la documentation de chess_coach en conformité avec la version actuelle de project_template."
status: implemented
superseded-by:
work-item:
tags: [python, tooling]
timestamp: 2026-08-23
perimeter: project
audience: []
---

# Réalignement de chess_coach sur project_template

## Objectif

`chess_coach` a été généré depuis une version ancienne de `project_template`,
qui a depuis été entièrement refondue (6 phases + branches correctives). Le
projet n'est pas rattaché au template (pas de `.cruft.json`) et a divergé sur
la forme (pas de pre-commit, `pyproject.toml`/`tasks.py` obsolètes, docs/
mal structurée) et sur le fond (`CLAUDE.md` décrit une architecture qui
n'existe plus : Lichess collector, caissAI runtime, `main.py`). Sans
réalignement, le repo accumule une dette d'outillage et un `CLAUDE.md` qui
induit l'agent en erreur à chaque session.

## Périmètre

### Inclus

- Rattachement au template (`.cruft.json` / `cruft link`)
- Fichiers de config/outillage manquants (pre-commit, markdownlint,
  prettier, gitattributes, changelog, contributing)
- `pyproject.toml` (dependency-groups, commitizen, ruff, coverage)
- `tasks.py` (tâches template : lint, precommit-install, test, docs,
  build, release)
- Arborescence `docs/` (specs/fixes/plans/_templates, `docs/code` Sphinx)
- Contexte `.claude/` (rules, commands, settings, DECISIONS/LESSONS
  reconstituées depuis le git log et le code)
- `okf-base.yaml` aligné sur le profil du template
- CI GitHub (`ci.yml`, `docs.yml` adapté à `docs/code/`)
- `CLAUDE.md` réécrit entièrement depuis le code source réel
- Corrections ponctuelles identifiées en diagnostic : doublon
  `src/chess_coach/bin/py.typed`, `_get_package_dir` ne couvrant pas
  `StopIteration` (Python 3.13)
- Première vague de tests unitaires sur les fonctions pures critiques

### Non-objectifs

Ce chantier ne change pas le comportement fonctionnel du programme : le
pipeline PGN annotés → profil de faiblesses → plan Claude → podcasts
podgenai reste inchangé. La migration vers `pydantic-settings` (à la place
de `player_config.yaml` + argparse) est un arbitrage séparé, hors périmètre
ici. Pas de wiki (`use_wiki=no`), pas de publication PyPI
(`publish_pypi=no`).

## Spécification fonctionnelle

- Le projet DOIT pouvoir exécuter `uv run inv lint`, `uv run inv test` et
  `uv run inv docs` sans erreur en fin de chantier.
- `uv run pre-commit run --all-files` DOIT être idempotent (deux passages
  consécutifs sans modification produite).
- Le comportement CLI observable (`chess_coach --pgn ... --list`,
  `--games N:M --dry-run`) DOIT rester inchangé.
- `CLAUDE.md` DOIT refléter exactement le code source réel, sans contenu
  inventé.

## Choix et contraintes

Décisions déjà arbitrées, non rediscutées ici : périmètres de linters
strictement disjoints (ruff/markdownlint-cli2/prettier), `inv lint`
délègue entièrement à pre-commit, `CLAUDE.md` reste à la racine,
`.claude/progress.log` append-only, Python figé à 3.13 — voir la consigne
du chantier pour le détail complet.

## Critères d'acceptation

- [x] `.cruft.json` présent, `cruft check` s'exécute sans erreur bloquante
- [x] `uv run pre-commit run --all-files` passe et est idempotent
- [x] `uv run inv lint` passe à zéro
- [ ] `uv run inv test` passe — non atteint : 3 échecs de doctests
      (`pgn_collector.list_games`, `pgn_filter.matches`,
      `tracker.init_db`) confirmés pré-existants et sans rapport avec ce
      chantier (fichiers sans diff en cours, échecs reproductibles sur
      HEAD seul) ; non corrigés, hors périmètre
- [x] `uv run inv docs` build Sphinx sans erreur depuis `docs/code/`
- [x] `CLAUDE.md` ne contient plus aucune référence à Lichess collector,
      caissAI runtime, `main.py`, ou `OPENAI_API_KEY`/`STOCKFISH_PATH`
      comme obligatoires
- [ ] `chess_coach --pgn <pgn> --list` et `--games 250:266 --dry-run`
      fonctionnent comme avant le chantier — non vérifié faute de PGN
      annoté disponible dans l'environnement ; `--help` et le pipeline
      d'argparse ont été testés, les fonctions de parsing exercées par
      les doctests
- [x] Doublon `src/chess_coach/bin/py.typed` supprimé
- [ ] `_get_package_dir` gère `StopIteration` — non applicable : testé
      directement sur Python 3.13.9 réel, le bug suspecté ne se
      reproduit pas (`ModuleNotFoundError` correctement levée) ; code
      laissé inchangé
