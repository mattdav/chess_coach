---
type: ProjectJournal
project: chess_coach
updated: 2026-08-23
tags: [python, chess, ai]
---

# Décisions

## 2026-08-23 — Réalignement complet sur project_template

Le projet a été réaligné sur l'état courant de `project_template` (tooling,
config, structure `docs/`, contexte `.claude/`), sans changement de
comportement fonctionnel du pipeline (lecture PGN caissAI → profil de
faiblesses → parties GM Lichess → plan Claude → podcasts podgenai).

- `docs/source/` renommé en `docs/code/` (convention du template pour la
  doc Sphinx générée depuis le code).
- `.github/workflows/lint.yml` supprimé au profit de `.github/workflows/ci.yml`
  (le template consolide lint/test/docs dans un seul workflow CI).
- `okf-base.yaml` : suppression de `status_field: "status"` et de
  `link_resolution.scope: base`, deux clés absentes du schéma lu par la
  version installée d'`okflint` (vérifié — aucun effet, pas de
  régression). Ajout de commentaires explicatifs sur chacun des 8 types
  du profil.

## 2026-08-23 — Non-migration vers pydantic-settings

`config/` ne contient aujourd'hui aucune classe `Settings` ni usage de
`pydantic-settings`, alors que le template recommande ce pattern.
Décision : ne pas migrer dans le cadre de ce réalignement.

**Pourquoi** : migrer impliquerait de toucher chaque module qui lit la
configuration ad hoc (variables d'environnement, YAML) — refactor
substantiel hors périmètre d'un simple alignement d'outillage, et rule 8
(pas de changement fonctionnel sans le signaler) interdit de le faire
sans validation explicite.

**Comment l'appliquer** : si une prochaine tâche touche `config/`,
proposer la migration comme chantier séparé plutôt que de la faire en
passant.

## 2026-08-23 — Tests laissés en infrastructure seule

`tests/` ne contient qu'un `__init__.py` placeholder ; aucune suite de
tests n'a été écrite dans le cadre de ce réalignement.

**Pourquoi** : écrire des tests substantiels n'était pas demandé et
aurait constitué du scope creep (règle 4 — code minimum). Le job `test`
du nouveau `ci.yml` échouera probablement (« no tests collected ») tant
que ce chantier n'est pas fait séparément.

**Comment l'appliquer** : signaler cet état à chaque intervention sur
`ci.yml` ou `tests/` tant qu'aucune suite réelle n'existe.
