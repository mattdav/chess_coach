---
type: Fix
id: FIX-001
title: "Trois doctests échouent sur uv run inv test"
description: "tracker.init_db, pgn_collector.list_games et pgn_filter.matches échouent, indépendamment du réalignement template."
status: confirmed
severity: major
work-item:
tags: [python, tests]
timestamp: 2026-08-23
perimeter: project
audience: []
---

# Trois doctests échouent sur `uv run inv test`

## Symptôme

`uv run inv test` échoue avec 3 doctests en échec :

- `chess_coach.bin.tracker.init_db`
- `chess_coach.bin.pgn_collector.list_games`
- `chess_coach.bin.pgn_filter.matches`

Ces échecs sont antérieurs au réalignement sur `project_template`
(FIX-001 est ouvert séparément de SPEC-001/PLAN-001) : les trois fichiers
concernés n'ont aucun diff en cours au moment du diagnostic, les échecs
sont donc reproductibles sur `HEAD` seul.

## Reproduction

```bash
uv run inv test
```

sur l'état courant du dépôt (aucune modification locale requise).

## Comportement attendu

Les trois doctests doivent passer, sans changement du comportement
observable des fonctions testées (schéma SQLite, format d'affichage
CLI, sémantique du filtre PGN) sauf arbitrage explicite documenté
ci-dessous.

## Analyse

Trois causes distinctes, sans rapport entre elles :

1. **`tracker.init_db`** — la table `puzzle_sessions` déclare
   `id INTEGER PRIMARY KEY AUTOINCREMENT`, ce qui fait créer par SQLite
   une table interne `sqlite_sequence` dès la création du schéma. La
   requête du doctest sur `sqlite_master` la retourne donc en plus des
   deux tables métier attendues. `AUTOINCREMENT` est un choix légitime
   du schéma ; c'est le doctest qui doit filtrer explicitement les
   tables internes.

2. **`pgn_collector.list_games`** — la fonction fait
   `print(f"{len(games)} partie(s) trouvée(s).\n")`, donc la sortie
   comporte une ligne vide finale (séparateur voulu avant la liste des
   parties) que le doctest ne déclare pas via `<BLANKLINE>`.

3. **`pgn_filter.matches`** — désaccord réel entre le doctest et le
   code : le doctest attend
   `matches(game, PgnFilter(min_opponent_elo=1700)) == False`, mais le
   code n'applique le critère Elo que si `player_name` est également
   renseigné (`if pgn_filter.min_opponent_elo > 0 and pgn_filter.player_name:`)
   — sans nom de joueur, le camp de l'adversaire n'est pas déterminable,
   donc le critère est silencieusement ignoré et la fonction retourne
   `True`. Nécessite un arbitrage (doctest à corriger vs. code à
   corriger) avant résolution — voir Résolution.

## Impact

Bloque `uv run inv test` en local et ferait échouer le job `test` du
workflow CI (`ci.yml`) dès le premier push. Aucun impact sur le
comportement runtime du programme (uniquement des doctests).

## Résolution

1. **`tracker.init_db`** — corrigé. Le doctest filtre désormais
   explicitement les tables internes SQLite
   (`WHERE type='table' AND name NOT LIKE 'sqlite_%'`) plutôt que
   d'ajouter `sqlite_sequence` au résultat attendu. Le schéma
   (`AUTOINCREMENT`) est inchangé. Épisode consigné dans
   `.claude/LESSONS.md`.
