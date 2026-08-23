# chess_coach

> Coach d'échecs IA — lit vos parties annotées par caissAI et génère un plan d'entraînement hebdomadaire personnalisé.

[![Python](https://img.shields.io/badge/python-3.13+-3670A0?style=flat&logo=python&logoColor=ffdd54)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Vue d'ensemble

chess_coach lit un fichier PGN de parties **déjà annotées par caissAI**, en extrait votre profil de faiblesses, puis génère un plan d'entraînement hebdomadaire actionnable via Claude (Anthropic).

```text
PGN annoté par caissAI
        │
        ▼
  Extraction des erreurs (NAGs caissAI)
        │
        ▼
  Profil de faiblesses (par phase, par ouverture ECO)
        │
        ▼
  Parties de GM sur vos ouvertures problématiques (Lichess Explorer)
        │
        ▼
  Plan d'entraînement 7 jours (Claude API)   +   Livrable Markdown
        │
        ▼
  Podcasts pédagogiques (podgenai, optionnel)  +  Snapshot SQLite
```

---

## Prérequis

| Outil | Rôle |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Gestion des dépendances |
| [caissAI](../caissAI) | Annotation des parties (doit être installé côte à côte) |
| Clé [Anthropic](https://console.anthropic.com/settings/keys) | Génération du plan Claude |
| Token [Lichess](https://lichess.org/account/oauth/token) | Parties de GM *(optionnel)* |
| [ffmpeg](https://ffmpeg.org/download.html) | Podcasts *(optionnel)* |

> **Workflow recommandé :** annoter vos parties avec caissAI d'abord (`uv run caissAI --pgn ... --games ...`), puis les passer à chess_coach.

---

## Installation

```bash
git clone <url>/caissAI   ../caissAI   # les deux projets côte à côte
git clone <url>/chess_coach
cd chess_coach
uv sync
```

### Configurer

```bash
cp .env.example .env
# Éditer .env
```

| Variable | Obligatoire | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Oui | Clé API Claude |
| `LICHESS_TOKEN` | Recommandé | Token OAuth Lichess (parties de GM) |
| `CAISSAI_CONFIG_PATH` | Non | Dossier `config/` de caissAI (détection auto) |
| `PLAYER_NAME` | Non | Défaut pour `--player` |
| `PLAYER_ELO` | Non | Défaut pour `--elo` |

Générer le token Lichess (lecture seule, sans scope particulier) : **https://lichess.org/account/oauth/token**

### Configurer le profil joueur

Éditez `src/chess_coach/config/player_config.yaml` pour y renseigner votre nom et votre Elo une bonne fois pour toutes :

```yaml
player:
  name: "Dupont"   # tel qu'il apparaît dans White / Black de vos PGN
  elo: 1650
```

Les arguments CLI `--player` et `--elo` surchargent ces valeurs si besoin.

---

## Utilisation

### Lister les parties d'un fichier

```bash
chess_coach --pgn "C:/ChessBase/mes parties.pgn" --list
```

### Lancer une session

```bash
# Toutes les parties du fichier
chess_coach --pgn "C:/ChessBase/mes parties.pgn"

# Parties sélectionnées par index (1-basé)
chess_coach --pgn "C:/ChessBase/mes parties.pgn" --games 184 185 186

# Filtrer sur un joueur (erreurs de ce joueur uniquement)
chess_coach --pgn "C:/ChessBase/mes parties.pgn" --player Dupont

# Avec podcasts pédagogiques
chess_coach --pgn "C:/ChessBase/mes parties.pgn" --games 184 --podcast

# Mode dry-run : extraction des erreurs sans appel Claude ni SQLite
chess_coach --pgn "C:/ChessBase/mes parties.pgn" --games 184 --dry-run
```

### Toutes les options

| Option | Description |
|---|---|
| `--pgn CHEMIN` | Fichier PGN annoté par caissAI *(obligatoire)* |
| `--games N [N …]` | Indices 1-basés des parties à analyser |
| `--player NOM` | Filtre par joueur, ne remonte que ses erreurs |
| `--list` | Liste numérotée des parties et quitte (sans clé API) |
| `--elo N` | Elo courant (défaut : `player_config.yaml` → `PLAYER_ELO`) |
| `--max-minutes N` | Durée max d'entraînement/jour (défaut : 45) |
| `--podcast` | Génère des podcasts podgenai |
| `--podcast-dir CHEMIN` | Dossier de sortie des MP3 |
| `--max-podcasts N` | Nombre max de podcasts (défaut : 3) |
| `--output-dir CHEMIN` | Dossier pour le plan Markdown et la base SQLite |
| `--dry-run` | Extrait les erreurs sans appel Claude ni écriture SQLite |

---

## Livrable

À chaque session, chess_coach génère `data/plans/YYYY-MM-DD_plan.md` :

```text
# Plan d'entraînement — 14 avril 2026

**Joueur :** Dupont  |  **Elo :** 1650  |  **Thème :** Tactiques de milieu de jeu

## Résumé d'analyse
| Indicateur | Valeur |
|---|---|
| Parties analysées | 21 |
| ACPL proxy moyen | 126.2 |
| Blunders | 32 |
| Phase la plus faible | middlegame |

### Ouvertures problématiques
| ECO | Ouverture | Erreurs |
|---|---|---|
| B31 | Sicilian Defense: Rossolimo | 21 |

### Positions clés à retravailler
**Position 1** — coup 31, phase : middlegame
- Coup joué : `e4e3` → **blunder**
- Meilleur coup : `b6d5`
- FEN : `4r1k1/pp1qp3/...` ← position AVANT le coup, à reproduire sur l'échiquier

## Plan hebdomadaire
### Lundi — Reconnaissance des patterns (45 min)
- **[puzzles]** Tactiques fourchette niveau 1500 (20 min)
  → https://lichess.org/training/fork

…

## Parties de grands maîtres à étudier
### B31 — Sicilian Defense: Rossolimo
- [Carlsen vs Nepomniachtchi (2021) 1-0](https://lichess.org/abc123)

## Bilan de semaine
- [ ] Objectifs atteints : *(à remplir)*
- Notes pour la session suivante : *(à remplir)*
```

Le FEN fourni dans les positions clés est celui **avant** le coup joué, ce qui permet de reproduire exactement la position sur l'échiquier pour s'entraîner.

---

## Architecture

```text
chess_coach/
├── .env                              # Secrets (jamais committé)
├── .env.example
├── pyproject.toml
└── src/chess_coach/
    ├── __main__.py                   # CLI argparse
    ├── main.py                       # (tombstone — remplacé par bin/session.py)
    ├── config/
    │   └── player_config.yaml        # Profil joueur (nom, elo, filtres)
    ├── bin/
    │   ├── analyzer.py               # Extraction erreurs depuis PGN annotés
    │   ├── coach.py                  # Plan d'entraînement via Claude API
    │   ├── gm_games.py               # Parties GM via Lichess Explorer API
    │   ├── pattern_detector.py       # Agrégation → WeaknessProfile
    │   ├── pgn_collector.py          # Lecture PGN + select_games / list_games
    │   ├── pgn_filter.py             # Moteur de filtrage déclaratif
    │   ├── player_config.py          # Lecture player_config.yaml
    │   ├── podcast_generator.py      # Podcasts via podgenai
    │   ├── report_writer.py          # Livrable Markdown
    │   ├── session.py                # Orchestrateur (ex-main.py)
    │   └── tracker.py                # SQLite : snapshots + tendance ACPL
    └── data/
        ├── plans/                    # Plans Markdown générés
        ├── chess_coach.db            # SQLite (gitignore)
        └── podcasts/                 # MP3 podgenai (gitignore)
```

---

## Points d'attention

**Pré-requis caissAI.** chess_coach ne lance aucune analyse Stockfish/Maia2 — il lit les annotations NAGs déjà posées par caissAI. Annotez vos parties avec caissAI en amont.

**Lichess Explorer API.** Depuis février 2026, `explorer.lichess.ovh/masters` requiert un token d'authentification. chess_coach tente `/masters` avec votre token, puis bascule automatiquement sur `/lichess` (ratings 2200+) en fallback si `/masters` est indisponible. Sans `LICHESS_TOKEN`, l'étape parties GM est simplement ignorée.

**FEN dans le plan.** Les positions clés sont exprimées en FEN **avant** le coup fautif, ce qui permet de les reproduire directement sur un échiquier ou dans un outil d'analyse.

**podgenai génère ~1h par topic.** Pour des tests rapides, limitez avec `--max-podcasts 1`.

---

## Développement

```bash
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
```

---

## Licence

MIT — voir [LICENSE](LICENSE).
