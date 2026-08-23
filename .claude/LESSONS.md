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
