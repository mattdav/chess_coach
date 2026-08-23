---
type: ProjectLifeCycle
project: chess_coach
status: active
updated: 2026-08-23
tags: [python]
---

# Changelog

All notable changes to chess_coach are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/).

This file is maintained automatically by [commitizen](https://commitizen-tools.github.io/commitizen/).
Do not manually edit the generated sections.

---

## [Unreleased]

### Refonte majeure de l'architecture

- **Suppression de Lichess comme source de parties** : chess_coach ne collecte plus de parties depuis l'API Lichess. Il lit uniquement des fichiers PGN déjà annotés par caissAI, passés via `--pgn`.
- **Suppression de caissAI comme dépendance runtime** : chess_coach ne lance plus Maia2 ni Stockfish. Il lit les NAGs et commentaires déjà présents dans les PGN caissAI. Les dépendances `caissAI`, `openai`, `psutil` retirées du `pyproject.toml`.
- **`main.py` → `bin/session.py`** : l'orchestrateur de session déplacé dans `bin/` ; `main.py` réduit à un tombstone.

### Nouveaux modules

- **`bin/session.py`** : orchestrateur de session avec pipeline 4 étapes (extraction → profil → GM + plan → podcasts/SQLite).
- **`bin/player_config.py`** : lecture de `player_config.yaml` exposant `PlayerConfig` (nom + elo) et `load_pgn_filter_from_config()`.
- **`bin/report_writer.py`** : génération du livrable Markdown `YYYY-MM-DD_plan.md` avec résumé d'analyse, plan jour par jour, positions clés (FEN avant le coup), parties GM et section bilan.
- **`config/player_config.yaml`** : fichier de configuration joueur centralisé (remplace `pgn_filter.yaml`).

### Améliorations CLI

- **`--pgn` obligatoire** : seule source de parties acceptée.
- **`--games N [N …]`** : sélection de parties par index 1-basé.
- **`--player NOM`** : filtre les erreurs au joueur indiqué ; défaut lu depuis `player_config.yaml` puis `PLAYER_NAME` dans `.env`.
- **`--elo N`** : défaut lu depuis `player_config.yaml` puis `PLAYER_ELO`.
- **`--list`** : affiche la liste numérotée sans nécessiter de clé API.
- **`--output-dir`** : dossier de sortie pour le plan Markdown et la base SQLite.
- Suppression de `--username`, `--max-games`, `--perf-types`, `--workers`, `--device`, `--save-pgn`.

### Corrections et améliorations

- **FEN dans `MoveError`** : corrigé pour pointer sur la position **avant** le coup joué (était après), permettant de reproduire la position sur un échiquier.
- **`pattern_detector.py`** : `problematic_openings` passe de `list[tuple[str, int]]` à `list[tuple[str, str, int]]` (eco, nom, nb_erreurs) ; agrégation par **code ECO** (header `[ECO]` toujours présent dans caissAI) plutôt que par nom d'ouverture (souvent `"Unknown"`).
- **`analyzer.py`** : `GameReport` enrichi du champ `eco: str` lu directement depuis le header `[ECO]` du PGN.
- **`gm_games.py`** : suppression de `build_eco_map` et de la navigation coup par coup. Le FEN est résolu directement depuis `lichess_eco.parquet` (déjà présent dans caissAI). Double endpoint : `/masters` avec token en priorité, `/lichess` (ratings 2200+) en fallback. Paramètre `since` corrigé au format `YYYY-MM`.
- **`LICHESS_TOKEN`** : nouvelle variable `.env` ; sans elle l'étape GM est ignorée (avertissement non bloquant).
- **`pandas` + `pyarrow`** : ajoutés aux dépendances pour lire `lichess_eco.parquet`.
- **`pgn_filter.yaml` → `player_config.yaml`** : renommage et enrichissement avec `player.elo`.
