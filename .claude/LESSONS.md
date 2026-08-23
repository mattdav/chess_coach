---
type: ProjectJournal
project: chess_coach
updated: 2026-08-23
tags: [python, chess, ai]
---

# Leçons apprises

## Ne pas faire confiance à un résumé pré-compaction sur l'état git sans revérifier

**Symptôme** : un résumé pré-compaction affirmait que
`.claude/DECISIONS.md` et `.claude/LESSONS.md` étaient « pré-existants,
propres, trackés par git ».

**Fausse piste** : partir de cette affirmation pour décider de ne pas y
toucher, en supposant qu'un `git add` classique suffirait s'il fallait
les inclure.

**Cause racine** : le résumé décrivait un état halluciné ou obsolète ;
`git ls-tree -r HEAD --name-only -- .claude` a montré que ces deux
fichiers n'avaient jamais été commités.

**Fix** : avant d'agir sur un fichier mentionné dans un résumé de
contexte, revérifier son état réel via `git ls-tree` / `git status`
plutôt que de faire confiance à la description héritée — surtout pour
tout ce qui touche au tracking git.

## markdownlint-cli2 --fix peut casser une phrase soft-wrappée commençant par « + »

**Symptôme** : une phrase de `CLAUDE.md`, écrite sur deux lignes dont la
seconde commençait par `+ NAGs...`, s'est retrouvée coupée par une ligne
vide insérée automatiquement par `markdownlint-cli2 --fix`, la
transformant en item de liste à puce isolé et cassant le rendu.

**Fausse piste** : croire que tout changement produit par `--fix` est
forcément une normalisation bénigne (comme le remplacement `-` → `+`
pour les puces, qui lui est correct) sans relire le diff après coup.

**Cause racine** : `--fix` interprète toute ligne commençant par `+`
(après une ligne vide ou en début de paragraphe) comme un marqueur de
liste, y compris quand ce n'est qu'une coïncidence de wrapping.

**Fix** : après tout `inv lint` qui modifie un fichier Markdown, relire
le diff produit avant de committer. Éviter de faire commencer une ligne
de texte par `+`, `-` ou `*` après un retour à la ligne manuel.

## Un conflit entre deux chantiers utilisateur distincts dans le même fichier justifie de s'arrêter, même sous autorisation large

**Symptôme** : `.gitignore` portait une ligne `.claude/` ajoutée par un
chantier utilisateur antérieur en cours (non lié à ce réalignement), qui
entrait en conflit avec la demande explicite de verser `.claude/` au
dépôt (Phase 6 du template).

**Fausse piste** : sous l'autorisation « va jusqu'au bout, je ferai un
contrôle global à la fin », trancher silencieusement (ex. retirer la
ligne sans demander, en supposant que c'est ce que l'utilisateur
voudrait).

**Cause racine** : une autorisation à procéder sans confirmation
intermédiaire porte sur les choix d'ingénierie ouverts du chantier en
cours — pas sur l'arbitrage entre deux chantiers séparés de
l'utilisateur, où une modification silencieuse risquerait d'écraser une
intention qui n'est pas la mienne à interpréter.

**Fix** : face à un conflit entre le chantier demandé et un autre
chantier utilisateur déjà en cours (visible via un diff pré-existant non
lié), toujours poser la question plutôt que d'arbitrer, même sous
autorisation large à « tout terminer ».

## AUTOINCREMENT crée une table sqlite_sequence qui apparaît dans sqlite_master

**Symptôme** (FIX-001) : le doctest de `tracker.init_db` attendait
`[('weekly_snapshots',), ('puzzle_sessions',)]` en interrogeant
`sqlite_master`, mais obtenait en plus `('sqlite_sequence',)`.

**Fausse piste** : chercher un bug dans le schéma (croire qu'une table
non déclarée est créée par erreur) ou étendre le résultat attendu du
doctest pour y inclure `sqlite_sequence`.

**Cause racine** : dès qu'une table déclare
`INTEGER PRIMARY KEY AUTOINCREMENT`, SQLite crée automatiquement une
table interne `sqlite_sequence` pour suivre le compteur — visible dans
`sqlite_master` comme n'importe quelle autre table. C'est un effet de
bord documenté de SQLite, pas un défaut du schéma.

**Fix** : quand un test interroge `sqlite_master` après un schéma
utilisant `AUTOINCREMENT`, filtrer explicitement les tables internes
(`WHERE type='table' AND name NOT LIKE 'sqlite_%'`) plutôt que de lister
`sqlite_sequence` dans le résultat attendu — l'intention testée reste
« mes tables métier existent », pas « SQLite gère bien son compteur
interne ».

## Un lint vert en local qui échoue en CI signale une dépendance à l'environnement, pas un faux positif

**Symptôme** : deux échecs CI consécutifs au premier push, tous deux
provenant d'étapes qui passaient localement.

1. `okflint` — `[L002] README.md — broken markdown link: ../caissAI`
2. `commitizen` — `No commit found with range: 'origin/main..HEAD'`

**Fausse piste** : dans les deux cas, conclure que l'outil se trompe et
chercher à le neutraliser — passer `broken_links` à `off` dans
`okf-base.yaml`, ou retirer le job commitizen. Le remède aurait supprimé
la détection sur tout le corpus documentaire pour un seul lien mal
formé, et la validation du format de commit pour un seul intervalle mal
calculé.

**Cause racine** : commune aux deux — une hypothèse implicite sur
l'environnement, vraie sur le poste de développement et fausse sur un
runner.

- `../caissAI` ne se résout que là où les deux dépôts sont clonés côte à
  côte. En CI, seul `chess_coach` est cloné. Le lien était en réalité
  cassé pour tout lecteur autre que son auteur : okflint avait raison.
- Sur un `push`, le runner clone le dépôt après intégration du push, donc
  `origin/main` et `HEAD` désignent le même commit et l'intervalle est
  vide. `origin/main..HEAD` n'est valide que dans le contexte d'une pull
  request.

**Fix** : traiter tout décalage local/CI comme le signal d'une dépendance
non déclarée à l'environnement local, et corriger la cause plutôt que de
désactiver le contrôle — URL absolue pour toute référence sortant du
dépôt, intervalle de commits dépendant de `github.event_name`. C'est la
même logique que le `template-ci.yml` de `project_template`, qui génère
depuis un clone frais et jamais depuis l'arbre de travail, précisément
pour rendre ces hypothèses visibles.

**Portée** : le correctif `ci.yml` a été reporté dans
`project_template` — le bug venait du template et aurait contaminé tous
les projets générés poussant directement sur `main`.
