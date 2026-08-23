---
type: ProjectStandards
project: chess_coach
updated: 2026-08-23
tags: [python, chess, ai]
---

# CLAUDE.md — chess_coach

Ce fichier guide Claude Code pour tous les travaux sur le projet `chess_coach`.

## Ce que fait chess_coach

`chess_coach` lit des parties **déjà annotées par caissAI** (Maia2, Stockfish
et NAGs, exécuté en amont, hors de ce projet) depuis un fichier PGN local,
et :

1. Extrait les erreurs à partir des NAGs présents dans le PGN — **aucune
   analyse n'est relancée ici**, caissAI doit avoir tourné avant.
2. Agrège les erreurs en profil de faiblesses (phases, catégories,
   ouvertures problématiques).
3. Récupère des parties de grands maîtres sur les ouvertures problématiques
   via l'API Lichess Opening Explorer.
4. Génère un plan d'entraînement hebdomadaire via l'API **Claude**.
5. Écrit le plan en Markdown (`data/plans/<date>_plan.md`).
6. Génère optionnellement des **podcasts pédagogiques** via **podgenai**.
7. Sauvegarde un snapshot (profil + plan) en **SQLite** et affiche la
   tendance ACPL par rapport à la semaine précédente.

Ce projet ne récupère **pas** les parties du joueur depuis un compte Lichess
en direct — `--pgn` (fichier local) est l'unique source des parties du
joueur. `LICHESS_TOKEN` sert uniquement à interroger l'API Lichess pour les
parties de **grands maîtres** de référence (étape 3), pas les parties du
joueur.

---

## Commandes CLI

```bash
# Lister les parties d'un fichier PGN (aucune clé API requise)
uv run chess_coach --pgn "C:/parties/mes parties.pgn" --list

# Analyser des parties précises (indices 1-basés, isolés ou en plage)
uv run chess_coach --pgn "C:/parties/mes parties.pgn" --games 3 7
uv run chess_coach --pgn "C:/parties/mes parties.pgn" --games 250:266

# Filtrer par joueur
uv run chess_coach --pgn "C:/parties/mes parties.pgn" --player Daviaud

# Session complète (toutes les parties du fichier) avec podcasts
uv run chess_coach --pgn "C:/parties/mes parties.pgn" --podcast --max-podcasts 2

# Dry-run : extraction des erreurs uniquement, sans Claude ni SQLite
uv run chess_coach --pgn "C:/parties/mes parties.pgn" --dry-run

# Qualité (source unique de vérité : pre-commit run --all-files)
uv run inv lint
```

---

## Architecture

```text
chess_coach/
├── CLAUDE.md
├── pyproject.toml
├── .env                        # Secrets (jamais committé)
├── .env.example                # Template
├── src/chess_coach/
│   ├── __init__.py
│   ├── __main__.py             # CLI argparse — dispatch vers bin.session.run_session
│   ├── bin/
│   │   ├── __init__.py
│   │   ├── analyzer.py         # report_from_pgn() — lit les NAGs, ne lance aucune analyse
│   │   ├── pattern_detector.py # build_weakness_profile() → WeaknessProfile
│   │   ├── pgn_collector.py    # read_games_from_file(), select_games(), list_games()
│   │   ├── pgn_filter.py       # PgnFilter déclaratif (voir « Sous-système non branché »)
│   │   ├── player_config.py    # load_player_config() — config/player_config.yaml
│   │   ├── gm_games.py         # fetch_opening_studies() — Lichess Opening Explorer
│   │   ├── coach.py            # generate_weekly_plan() via l'API Claude
│   │   ├── report_writer.py    # write_training_plan() → Markdown
│   │   ├── podcast_generator.py # generate_podcasts() via podgenai (optionnel)
│   │   ├── tracker.py          # SQLite snapshots + tendance ACPL
│   │   └── session.py          # run_session() — orchestrateur appelé par __main__
│   ├── config/
│   │   ├── __init__.py         # vide
│   │   └── player_config.yaml  # {player: {name, elo}}
│   ├── data/                   # DB SQLite, plans Markdown, podcasts (gitignore)
│   └── log/
└── tests/
```

---

## Pipeline d'exécution

```text
__main__.main()
    │
    ├── player_config.load_player_config()            # défauts --player/--elo
    ├── [si --list] pgn_collector.read_games_from_file() + list_games()  → exit
    ├── pgn_collector.read_games_from_file(pgn_path)   # toutes les parties du fichier
    ├── pgn_collector.parse_game_indices(--games)      # optionnel
    ├── pgn_collector.select_games(all_games, indices, player)
    │
    └── session.run_session(pgn_games=selected, player_elo, player_name,
                             lichess_token, caissai_config_path, ...)
            │
            ├── 1/4  analyzer.report_from_pgn(game, player_name) × N
            │           → GameReport (lecture des NAGs déjà présents)
            │
            ├── 2/4  pattern_detector.build_weakness_profile(reports)
            │           → WeaknessProfile
            │
            ├── [si --dry-run] → retour immédiat, rien en dessous n'est exécuté
            │
            ├── 3/4  gm_games.fetch_opening_studies(problematic_openings, lichess_token, ...)
            │           → list[OpeningStudy]  (Lichess Opening Explorer + export PGN)
            │
            │         coach.generate_weekly_plan(profile, player_elo, gm_studies, ...)
            │           → TrainingPlan (appel API Claude)
            │
            │         report_writer.write_training_plan(profile, plan, ..., gm_studies)
            │           → data/plans/<date>_plan.md
            │
            └── 4/4  [si --podcast] podcast_generator.generate_podcasts(plan, ...)
                         → MP3 via podgenai

                      tracker.init_db(db_path)
                      tracker.save_snapshot(conn, elo, profile, plan)
                      tracker.get_progress_trend(conn, weeks=4)   # tendance ACPL affichée
```

---

## Modules — détail

### `bin/pgn_collector.py`

+ `read_games_from_file(pgn_path)` → `list[chess.pgn.Game]` — utilisé par `__main__.py`.
+ `parse_game_indices(tokens)` → `list[int]` — parse `--games` (indices et/ou plages `N:M`).
+ `select_games(games, indices=None, player=None)` → `list[tuple[int, chess.pgn.Game]]`.
+ `list_games(games)` — affiche la liste numérotée (mode `--list`).
+ `load_pgn_files(...)` / `load_pgn_files_with_config(...)` : existent mais **ne sont
  appelées ni par `__main__.py` ni par `session.py`** — voir « Sous-système non branché ».

### `bin/analyzer.py`

+ `report_from_pgn(annotated_game, player_name="")` → `GameReport`.
+ Ne lance **aucune** analyse : lit les NAGs, commentaires et variations déjà
  présents dans le PGN annoté par caissAI.
+ Mapping NAG → `MoveError.category` / `cp_loss` (proxy) :

| NAG | Constante python-chess | Catégorie | Proxy cp_loss |
| --- | --- | --- | --- |
| `$5` | `NAG_DUBIOUS_MOVE` | `"dubious"` | 75 |
| `$2` | `NAG_MISTAKE` | `"mistake"` | 150 |
| `$4` | `NAG_BLUNDER` | `"blunder"` | 300 |

Le meilleur coup (`MoveError.best`) est lu dans la variation alternative du
nœud parent (`_best_move_from_variation`), c'est-à-dire la suggestion de
caissAI.

### `bin/pattern_detector.py`

+ `build_weakness_profile(reports)` → `WeaknessProfile`.
+ `problematic_openings` est agrégé par **code ECO** (top 5), pas par nom
  d'ouverture.
+ `worst_positions` : top 10 `MoveError` toutes parties confondues.
+ `annotated_pgns` : PGN complets — **jamais envoyés à Claude** (trop longs),
  disponibles pour sauvegarde/consultation.

### `bin/gm_games.py`

+ `fetch_opening_studies(problematic_openings, lichess_token, caissai_config_path=None, max_games_per_opening=3, max_openings=3)` → `list[OpeningStudy]`.
+ Interroge l'API Lichess Opening Explorer (`/masters`, repli `/lichess`
  filtré Elo 2200-2500) puis télécharge le PGN complet de chaque partie
  (`lichess.org/game/export/<id>`).
+ Résout le FEN d'un code ECO via `lichess_eco.parquet`, un fichier qui vit
  dans le projet **caissAI** séparé (chemin relatif par défaut, ou
  `--caissai-config-path`/`CAISSAI_CONFIG_PATH`).
+ Nécessite `LICHESS_TOKEN` : sans token, l'appel de repli `/lichess` est
  aussi ignoré et la fonction renvoie une liste vide.

### `bin/coach.py`

+ `generate_weekly_plan(profile, player_elo, max_daily_minutes=45, model=..., gm_studies=None)` → `TrainingPlan`.
+ Un seul point d'appel Claude dans tout le projet (`anthropic.Anthropic().messages.create`,
  client singleton lazy). Modèle par défaut : env `ANTHROPIC_MODEL`, sinon
  `claude-sonnet-4-5`.
+ Le prompt embarque le profil sérialisé (sans `annotated_pgns`) et un résumé
  des `OpeningStudy` GM si fournis.

### `bin/report_writer.py`

+ `write_training_plan(profile, plan, player_name, player_elo, output_dir, gm_studies=None)` → `Path`.
+ Écrit `output_dir/<YYYY-MM-DD>_plan.md` : résumé d'analyse, plan
  hebdomadaire, parties GM de référence, checklist de bilan à remplir
  manuellement.

### `bin/podcast_generator.py`

+ `extract_podcast_topics(plan, player_elo, max_topics=3)` → `list[str]`.
+ `generate_podcasts(plan, player_elo, output_dir, max_topics=3, max_sections=None)` → `list[Path]`.
+ Import de `podgenai` gardé en lazy (`ImportError` explicite si absent).
+ Contient un contournement documenté (`_configure_podgenai_model`) pour un
  modèle OpenAI figé et obsolète en dur dans podgenai 0.17.2.
+ **Prérequis** : `podgenai` (extra `podcast`), `ffmpeg` dans le PATH,
  `OPENAI_API_KEY` dans l'environnement.

### `bin/tracker.py`

+ `init_db(db_path)` → `sqlite3.Connection`.
+ `save_snapshot(conn, elo, profile, plan)` (clé : date du jour, `INSERT OR REPLACE`).
+ `get_progress_trend(conn, weeks=8)` → `list[dict]`.
+ La table `puzzle_sessions` est créée par le schéma mais **rien n'écrit
  dedans actuellement**.

### `bin/player_config.py`

+ `load_player_config(config_path=None)` → `PlayerConfig` (défauts `--player`/`--elo` depuis `config/player_config.yaml`).
+ `load_pgn_filter_from_config(...)` existe mais n'est appelée par rien dans
  le flux CLI actuel — voir ci-dessous.

### Sous-système non branché : `pgn_filter.py`

`pgn_filter.py` (filtrage déclaratif via `config/pgn_filter.yaml`),
`pgn_collector.load_pgn_files`/`load_pgn_files_with_config` et
`player_config.load_pgn_filter_from_config` forment un mécanisme complet et
doctesté, mais **non appelé** par `__main__.py` ni `session.py` — la
sélection des parties passe uniquement par `select_games` (indices +
`--player`). `config/pgn_filter.yaml` n'existe pas sur disque. À ne pas
utiliser comme référence pour comprendre le flux réel ; ne pas le brancher
ni le supprimer sans consigne explicite (changement fonctionnel hors
périmètre d'un simple alignement de tooling).

---

## Types importants

```python
# analyzer.py
@dataclass
class MoveError:
    fen: str
    played: str       # UCI
    best: str         # UCI (variante caissAI)
    cp_loss: int       # proxy : 75 / 150 / 300
    category: str      # "dubious" | "mistake" | "blunder"
    phase: str         # "opening" | "middlegame" | "endgame"
    move_number: int
    comment: str = ""  # commentaire caissAI

@dataclass
class GameReport:
    game_id: str
    opening: str
    eco: str = ""
    errors: list[MoveError] = field(default_factory=list)
    acpl: float = 0.0
    annotated_pgn: str = ""

# pattern_detector.py
class WeaknessProfile(TypedDict):
    total_games: int
    avg_acpl: float
    weakest_phase: str
    phase_breakdown: dict[str, int]
    category_breakdown: dict[str, int]
    problematic_openings: list[tuple[str, str, int]]  # (eco, nom, nb_erreurs)
    avg_cp_loss_by_phase: dict[str, float]
    worst_positions: list[MoveError]
    annotated_pgns: list[str]

# gm_games.py
@dataclass
class GmGameRef:
    game_id: str
    white: str
    black: str
    year: int
    winner: str   # "white" | "black" | "draw"
    eco: str
    opening_name: str
    pgn: str = ""

@dataclass
class OpeningStudy:
    eco: str
    opening_name: str
    games: list[GmGameRef] = field(default_factory=list)

# coach.py
class DailyExercise(TypedDict):
    type: str          # "puzzles"|"game_analysis"|"opening_study"|"endgame"
    description: str
    duration_min: int
    lichess_url: str

class DailyTask(TypedDict):
    day: str
    focus: str
    exercises: list[DailyExercise]

class TrainingPlan(TypedDict):
    week_theme: str
    daily_tasks: list[DailyTask]
    key_concepts: list[str]
    success_metrics: str
```

---

## Variables d'environnement

| Variable | Obligatoire | Usage |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Oui | Claude — génération du plan d'entraînement |
| `LICHESS_TOKEN` | Non | Parties GM de référence (`gm_games.py`) — sans token, cette étape ne renvoie rien |
| `CAISSAI_CONFIG_PATH` | Non | Chemin vers la config caissAI (résolution de `lichess_eco.parquet`) |
| `PLAYER_NAME` | Non | Surcharge `--player` / `config/player_config.yaml` |
| `PLAYER_ELO` | Non | Surcharge `--elo` / `config/player_config.yaml` |
| `OPENAI_API_KEY` | Non (requis si `--podcast`) | podgenai (TTS) |

---

## Points d'attention

1. **Aucune analyse d'échecs n'est faite dans ce projet** : le PGN d'entrée
   doit déjà être annoté par caissAI (NAGs + variations). `chess_coach` ne
   lance ni Maia2 ni Stockfish.
2. **`gm_games.py` dépend du projet `caissAI`** (chemin relatif par défaut
   vers `lichess_eco.parquet`, ou `CAISSAI_CONFIG_PATH`) — ne pas dupliquer
   ce fichier dans `chess_coach`.
3. **podgenai génère un contenu long** par sujet ; utiliser `max_sections`
   pour des tests plus courts.
4. **Coûts API** : Claude (plan) + OpenAI (podgenai TTS si `--podcast`)
   peuvent s'accumuler. `--dry-run` évite Claude, SQLite et les parties GM.
5. **ffmpeg obligatoire pour podgenai** : doit être dans le PATH système.
6. **`beartype` est listé en dépendance** (`pyproject.toml`) mais **n'est
   utilisé nulle part dans `src/`** actuellement — écart connu, non corrigé
   dans le cadre d'un alignement de tooling (changement fonctionnel hors
   périmètre).

---

## Standards de qualité

+ Mypy strict (`strict = true`) : 0 erreur.
+ Ruff : 0 warning.
+ Type hints et docstrings Google sur toutes les fonctions publiques.
+ `uv run inv lint` (délègue à `pre-commit run --all-files`) doit passer à
  zéro avant tout commit.

## Règles importantes pour Claude Code

1. **Ne jamais committer `.env`**.
2. **Ne pas dupliquer caissAI** — importer/référencer, ne pas recopier
   `lichess_eco.parquet` ni relancer une analyse.
3. **podgenai derrière `try/except ImportError`** — dépendance optionnelle
   (extra `podcast`).
4. **Ne pas brancher `pgn_filter.py`/`pgn_filter.yaml`** sans consigne
   explicite — sous-système présent mais volontairement non utilisé
   actuellement.
5. **Langue** : identifiants Python en anglais, commentaires et docstrings
   en français.
