# CLAUDE.md — chess_coach

Ce fichier guide Claude Code pour tous les travaux sur le projet `chess_coach`.

## Ce que fait chess_coach

`chess_coach` est un projet autonome de coaching aux échecs. Il :
1. Collecte les parties d'un joueur depuis **deux sources** :
   - API Lichess (filtrée par cadence — exclure blitz/bullet si désiré)
   - Fichiers PGN locaux (parties officielles de tournois / club)
2. Annote chaque partie avec **caissAI** (Maia2 + Stockfish + NAGs) :
   - Lichess → `comment=False` (rapide, sans GPT)
   - Officielles → `comment=True` (résumé GPT complet)
3. Agrège les erreurs en profil de faiblesses par phase et par source
4. Génère un plan d'entraînement hebdomadaire via l'API **Claude**
5. Génère des **podcasts pédagogiques** via **podgenai** (optionnel)
6. Sauvegarde le snapshot dans **SQLite**

Ce projet est distinct de `chess_toolbox` (`../chess_toolbox`) qui ne contient
que des utilitaires d'administration PGN.

---

## Commandes CLI

```bash
# Session minimale (toutes les cadences Lichess)
uv run chess_coach --username mon_pseudo --elo 1650

# Exclure blitz et bullet (ne garder que parties sérieuses)
uv run chess_coach --perf-types rapid classical correspondence

# Ajouter des parties officielles PGN (annotées avec comment=True)
uv run chess_coach --pgn C:/parties/tournoi.pgn C:/parties/club/

# Sauvegarder les PGN annotés par caissAI
uv run chess_coach --pgn C:/parties/ --save-pgn C:/parties/annotes/

# Générer des podcasts podgenai sur les sujets du plan
uv run chess_coach --podcast --max-podcasts 2 --podcast-dir C:/podcasts/

# Session complète
uv run chess_coach \
    --perf-types rapid classical \
    --pgn C:/parties/tournoi.pgn \
    --save-pgn C:/parties/annotes/ \
    --podcast \
    --max-podcasts 3

# Dry-run (annotation caissAI sans Claude ni SQLite)
uv run chess_coach --dry-run --max-games 5

# Qualité
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
```

---

## Architecture

```
chess_coach/
├── CLAUDE.md
├── pyproject.toml
├── .env                        # Secrets (jamais committé)
├── .env.example                # Template
├── src/chess_coach/
│   ├── __init__.py
│   ├── __main__.py             # CLI argparse — dispatch vers main.run_weekly_session
│   ├── main.py                 # Orchestrateur complet (5 étapes)
│   ├── bin/
│   │   ├── __init__.py
│   │   ├── analyzer.py         # Pont caissAI → GameReport (comment param)
│   │   ├── coach.py            # Génération plan via Claude API
│   │   ├── lichess_collector.py # fetch_games() avec filtre perf_types
│   │   ├── pgn_collector.py    # load_pgn_files() — parties officielles
│   │   ├── pattern_detector.py # build_weakness_profile() → WeaknessProfile
│   │   ├── podcast_generator.py # generate_podcasts() via podgenai
│   │   └── tracker.py          # SQLite snapshots + tendance ACPL
│   ├── data/
│   │   ├── chess_coach.db      # SQLite (gitignore)
│   │   ├── podcasts/           # MP3 podgenai (gitignore)
│   │   └── annotated/          # PGN annotés caissAI (gitignore)
│   ├── log/
│   └── py.typed
└── tests/
```

---

## Pipeline d'exécution

```
__main__.main()
    │
    ├── load_maia2_model()              # une seule fois
    ├── OpenAI(api_key=...)             # une seule fois
    │
    └── main.run_weekly_session(...)
            │
            ├── 1. Collecte
            │   ├── lichess_collector.fetch_games(perf_types=[...])
            │   │       → list[chess.pgn.Game]   source="lichess"
            │   └── pgn_collector.load_pgn_files([...])
            │           → list[chess.pgn.Game]   source="official"
            │
            ├── 2. Annotation caissAI
            │   ├── analyzer.analyze_game(comment=False, source="lichess") × N
            │   └── analyzer.analyze_game(comment=True,  source="official") × M
            │           → GameReport (errors, acpl, annotated_pgn, source)
            │
            ├── 3. Profil de faiblesses
            │   └── pattern_detector.build_weakness_profile(reports)
            │           → WeaknessProfile (phase, category, source breakdown)
            │
            ├── 4. Plan d'entraînement
            │   └── coach.generate_weekly_plan(profile, elo)
            │           → TrainingPlan (Claude API)
            │
            ├── 5. Podcasts (si --podcast)
            │   └── podcast_generator.generate_podcasts(plan, elo, dir)
            │           → list[Path]  (MP3 via podgenai)
            │
            └── 6. Persistance
                └── tracker.save_snapshot(conn, elo, profile, plan)
```

---

## Modules — détail

### `bin/lichess_collector.py`

- `fetch_games(username, max_games, rated_only, perf_types)` → `list[chess.pgn.Game]`
- `perf_types` : liste de cadences passée à l'API Lichess comme `perfType`.
  Valeurs : `"bullet"`, `"blitz"`, `"rapid"`, `"classical"`, `"correspondence"`,
  `"chess960"`. `None` = toutes les cadences.
- Streaming NDJSON : parse le champ `pgn` de chaque objet JSON ligne par ligne.

### `bin/pgn_collector.py`

- `load_pgn_files(pgn_paths, recursive=False)` → `list[chess.pgn.Game]`
- Accepte des fichiers `.pgn` individuels **et** des dossiers.
- Parties chargées brutes — `analyze_game` les nettoie avant caissAI.

### `bin/analyzer.py`

- `analyze_game(game, config_path, engine_path, maia2_model, openai_client,
  n_workers, username, comment, source)` → `GameReport`
- **`comment=False`** pour Lichess (pas d'appel GPT — rapide).
- **`comment=True`** pour les officielles (résumé GPT caissAI complet).
- **`source`** : propagé dans `GameReport.source` pour le `source_breakdown`.
- `extract_report_from_annotated_game(game, username)` : lit les NAGs de la
  partie annotée et crée les `MoveError`.
- `load_maia2_model(device)` et `default_n_workers()` : helpers d'initialisation.

**Mapping NAG → MoveError** :

| NAG | Constante python-chess | Catégorie | Proxy cp_loss |
|---|---|---|---|
| `$5` | `NAG_DUBIOUS_MOVE` | `"dubious"` | 75 |
| `$2` | `NAG_MISTAKE` | `"mistake"` | 150 |
| `$4` | `NAG_BLUNDER` | `"blunder"` | 300 |

Bons coups et coups forcés ignorés. Le meilleur coup est lu dans la **variation
alternative du nœud parent** (`_best_move_from_variation`).

### `bin/pattern_detector.py`

- `build_weakness_profile(reports)` → `WeaknessProfile`
- `WeaknessProfile` contient `source_breakdown` (`{"lichess": N, "official": M}`)
  en plus des breakdowns habituels phase/catégorie.
- Les PGN annotés sont agrégés dans `annotated_pgns` (liste de strings) —
  **non envoyés à Claude** (trop longs), disponibles pour sauvegarde disque.

### `bin/coach.py`

- `generate_weekly_plan(profile, player_elo, max_daily_minutes, model)` → `TrainingPlan`
- Le prompt envoie : stats agrégées + 10 pires positions avec leur commentaire
  caissAI (`caissai_comment`).
- Claude reçoit le contexte pédagogique caissAI pour personnaliser le plan
  au-delà des simples statistiques.

### `bin/podcast_generator.py`

- `extract_podcast_topics(plan, player_elo, max_topics)` → `list[str]`
  Extrait `week_theme` puis `key_concepts`, formatés avec le niveau Elo.
- `generate_podcasts(plan, player_elo, output_dir, max_topics, max_sections)`
  → `list[Path]`
  Appelle `podgenai.generate_media(topic, output_path=dir)` pour chaque sujet.
  Retourne None sans lever d'exception si podgenai n'est pas installé.
- **Prérequis** : `podgenai` (`uv pip install podgenai`), `ffmpeg` dans le PATH,
  `OPENAI_API_KEY` dans l'environnement.

### `bin/tracker.py`

- `init_db(db_path)` → `sqlite3.Connection` (crée tables si absent)
- `save_snapshot(conn, elo, profile, plan)` (clé : date du jour)
- `get_progress_trend(conn, weeks)` → `list[dict]` (ACPL des N dernières semaines)

---

## Types importants

```python
# analyzer.py
@dataclass
class MoveError:
    fen: str
    played: str       # UCI
    best: str         # UCI (variante caissAI)
    cp_loss: int      # proxy : 75 / 150 / 300
    category: str     # "dubious" | "mistake" | "blunder"
    phase: str        # "opening" | "middlegame" | "endgame"
    move_number: int
    comment: str      # commentaire caissAI (espérance de gain)

@dataclass
class GameReport:
    game_id: str
    opening: str
    errors: list[MoveError]
    acpl: float
    annotated_pgn: str   # PGN complet caissAI
    source: str          # "lichess" | "official" | "pgn"

# pattern_detector.py
class WeaknessProfile(TypedDict):
    total_games: int
    avg_acpl: float
    weakest_phase: str
    phase_breakdown: dict[str, int]
    category_breakdown: dict[str, int]   # blunder/mistake/dubious
    source_breakdown: dict[str, int]     # lichess/official
    problematic_openings: list[tuple[str, int]]
    avg_cp_loss_by_phase: dict[str, float]
    worst_positions: list[MoveError]
    annotated_pgns: list[str]

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

## Intégration caissAI (CRITIQUE)

caissAI est installé comme dépendance locale :
```bash
uv pip install -e ../caissAI
```

**Règle absolue** : Maia2 et le client OpenAI sont initialisés **une seule fois**
dans `__main__.py` et passés par injection à `analyze_game()`. Ne jamais les
instancier dans `analyzer.py` ou `main.py`.

`process_game` est appelé avec `comment=False` (Lichess) ou `comment=True`
(officielles). Avec `comment=True`, caissAI appelle GPT pour un résumé de la
partie — plus lent et plus coûteux.

---

## Intégration podgenai

podgenai est une dépendance optionnelle :
```bash
uv pip install podgenai
# ou
uv sync --extra podcast
```

L'import est gardé dans `podcast_generator.py` derrière un `try/except ImportError`
pour que le reste de chess_coach fonctionne sans podgenai installé.

**Ne jamais appeler `generate_media` directement depuis `main.py`** — passer par
`podcast_generator.generate_podcasts()` qui gère l'import conditionnel, les
erreurs podgenai, et le formatage des topics.

---

## Variables d'environnement

| Variable | Obligatoire | Usage |
|---|---|---|
| `ANTHROPIC_API_KEY` | Oui | Claude — plan d'entraînement |
| `OPENAI_API_KEY` | Oui | caissAI (même sans GPT) + podgenai |
| `STOCKFISH_PATH` | Oui | Chemin Stockfish |
| `LICHESS_USERNAME` | Non | Défaut CLI `--username` |
| `PLAYER_ELO` | Non | Défaut CLI `--elo` |
| `CAISSAI_CONFIG_PATH` | Non | Détection auto si caissAI installé |

---

## Points d'attention

1. **caissAI est lent** : plusieurs minutes par partie. `comment=True` est
   encore plus lent (appel GPT). Limiter les parties officielles à ce qui est
   vraiment utile.
2. **podgenai génère ~1h de contenu** par topic. Utiliser `max_sections`
   dans `generate_podcasts()` pour des tests plus courts (min : 3).
3. **Lichess streaming NDJSON** : peut timeout sur les grandes collections.
   Gérer `httpx.ReadTimeout` — déjà fait dans `lichess_collector.py`.
4. **Coûts API** : Claude (plan) + OpenAI (caissAI comment=True + podgenai TTS)
   peuvent s'accumuler. Le `--dry-run` évite tous les appels IA sauf caissAI.
5. **ffmpeg obligatoire pour podgenai** : doit être dans le PATH système.
6. **SQLite** : `init_db()` crée la base si elle n'existe pas.

---

## Standards de qualité

- `@beartype` sur toutes les fonctions publiques
- Mypy strict (`strict = true`) : 0 erreur
- Ruff : 0 warning
- Docstrings Google style avec `Examples:` sur toutes les fonctions publiques
- `inv lint` depuis le répertoire parent avant tout commit

## Règles importantes pour Claude Code

1. **Ne jamais committer `.env`**
2. **Ressources lourdes par injection** — Maia2 et OpenAI dans `__main__.py` uniquement
3. **Ne pas dupliquer caissAI** — importer, ne pas recopier
4. **podgenai derrière `try/except ImportError`** — dépendance optionnelle
5. **`source` sur GameReport** — toujours renseigner ("lichess" | "official" | "pgn")
6. **Langue** : identifiants Python en anglais, commentaires et docstrings en français
