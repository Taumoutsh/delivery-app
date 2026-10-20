# Checklist de livraison — Spécifications

Document de référence à relire avant toute évolution. Il décrit le besoin, les choix
techniques et l'état actuel. Mettre à jour la section « Journal » à chaque évolution.

## 1. Besoin

Application web locale servant de checklist pour préparer une livraison logicielle.

| # | Exigence | État |
|---|----------|------|
| E1 | Application web, petite base de données, backend Python | ✅ |
| E2 | Ajout facile de tâches : titre, description, ligne(s) de commande copiable(s) | ✅ |
| E3 | Les commandes s'adaptent à la version livrée (variables `{{version}}`…) | ✅ |
| E4 | Lancement facile et autonome depuis un script, dans un dossier précis | ✅ `run.sh` / `run.bat` |
| E5 | Specs conservées dans un `.md` (ce fichier) | ✅ |
| E6 | Barre de progression pondérée (chaque tâche a un poids) | ✅ |
| E7 | Valider une tâche la replie ; possibilité de la déplier | ✅ |
| E8 | Temps estimé + temps passé (chrono démarré par l'action « Démarrer ») | ✅ |
| E9 | Commentaires par tâche, pour chaque livraison | ✅ |
| E10 | Export d'un rapport de fin : PDF et Word | ✅ |
| E11 | Toutes les livraisons historisées et accessibles en base | ✅ |
| E12 | Une ou plusieurs images par tâche (miniature, agrandie à la demande) | ✅ |
| E13 | Pour certaines tâches, générer un tableau avec liens à insérer dans un document Word | ✅ copie riche + .docx |
| E14 | Tout embarquer : l'environnement cible n'exécute qu'un Python (pas de pip, pas d'internet) | ✅ stdlib uniquement |
| E15 | Plusieurs lignes de commande par tâche | ✅ blocs libellés, un bouton Copier chacun |
| E16 | Plusieurs éléments Word (tableaux) par tâche | ✅ tableaux titrés, copie/.docx un par un ou tous |

## 2. Concepts

- **Modèle de tâches** : la liste « maître » des tâches. Chaque nouvelle livraison en fait une
  **copie** (snapshot). Modifier le modèle ne réécrit jamais l'historique.
- **Livraison** : une version (ex. `2.4.0`), un nom optionnel, des variables personnalisées,
  un statut (`in_progress` / `done`), ses tâches, commentaires et images.
- **Tâche de livraison** : copie d'une tâche du modèle (ou tâche ajoutée à la volée), avec
  statut, chrono, commentaires, images. Modifiable sans toucher le modèle, avec option
  « Répercuter dans le modèle ».

### 2.1 Variables de commande

Syntaxe `{{nom}}` dans la commande **et** la description. Substitution à l'affichage, à la copie
et dans le rapport. Une variable inconnue reste telle quelle et est signalée (soulignée en rouge).

| Variable | Valeur |
|----------|--------|
| `{{version}}` | version saisie |
| `{{major}}`, `{{minor}}`, `{{patch}}` | segments de la version (séparateurs `.`, `-`, `+`) |
| `{{date}}` | date de création de la livraison `AAAA-MM-JJ` |
| `{{name}}` | nom de la livraison |
| `{{prev_version}}` | pré-rempli avec la version de la livraison précédente |
| personnalisées | définies par livraison (`clé = valeur`), pré-remplies depuis les « variables par défaut » du modèle |

Les variables personnalisées surchargent les variables intégrées.

### 2.2 Blocs de commande (E2, E15)

Une tâche porte une liste `commands` de blocs `{label, text}` (JSON en base). `label` est optionnel
(ex. « Linux », « Build ») et accepte les variables ; `text` peut faire plusieurs lignes. Chaque bloc a
son bouton Copier ; les blocs vides sont ignorés à l'enregistrement. Dans le formulaire : ajout,
retrait, monter/descendre.

### 2.3 Tableaux pour Word (E13, E16)

Une tâche porte une liste `link_tables` de tableaux `{title, spec}` (JSON en base) ; `title` est
optionnel. Syntaxe de `spec`, une rangée par ligne :

```
Élément | Lien
Notes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})
Tag Git | https://git.example.com/app/-/tags/v{{version}}
```

- Cellules séparées par `|` ; la 1re ligne donne les en-têtes ; `|` en début/fin et lignes `|---|` (style
  Markdown) ignorés ; rangées courtes complétées par des cellules vides.
- Liens : `[texte](url)` ou URL brute `http(s)://…` ; texte et liens peuvent se mélanger dans une cellule.
- Variables `{{…}}` substituées comme pour les commandes. Un `|` ne peut pas figurer dans une URL.
- Dans la tâche : aperçu de chaque tableau (avec son titre), puis pour chacun
  - **Copier pour Word** : presse-papiers HTML (styles en ligne : bordures, en-tête coloré, liens
    cliquables) + texte tabulé ; on colle directement dans Word. Repli `execCommand('copy')` si l'API
    Clipboard est refusée.
  - **Télécharger en .docx** : document contenant uniquement ce tableau (Word : Insertion › Objet ›
    Texte d'un fichier, ou copier-coller).
  - S'il y a plusieurs tableaux : **Copier tous les tableaux** / **Tous en .docx**, chaque tableau
    précédé de son titre.
- Le tableau figure aussi dans les rapports PDF (liens cliquables) et Word (hyperliens).
- Parseur en double : `templating.parse_table` (Python) et `parseTable` (`app.js`) — les garder alignés.

### 2.4 Statuts et chrono

`todo` → `running` ⇄ `paused` → `done` | `skipped` (non applicable).

- **Démarrer** : `running`, `running_since = now`, `started_at` fixé au premier démarrage.
- **Pause** : cumule `now - running_since` dans `elapsed_seconds`.
- **Valider** / **Non applicable** : cumule le temps, fixe `completed_at`, la tâche se replie.
- **Rouvrir** : revient à `paused` (ou `todo` si aucun temps passé).
- **Remettre à zéro** : statut `todo`, chrono à 0.
- Plusieurs tâches peuvent tourner en parallèle. Le temps est calculé côté serveur (UTC),
  l'interface rafraîchit l'affichage chaque seconde. Dépassement de l'estimé affiché en orange.

### 2.5 Progression

`progression = Σ poids(validées) / Σ poids(toutes sauf non applicables)`.
La barre est segmentée : un segment par tâche, largeur proportionnelle au poids, couleur selon
le statut. Affiche aussi tâches faites, poids, temps passé, estimé, reste estimé.

## 3. Architecture

```
run.sh / run.bat          lanceurs (venv + dépendances + ouverture navigateur)
launch.py                 lanceur Python (ouvre le navigateur ; --no-browser pour l'éviter)
delivery_app/
  __main__.py             CLI : --port (8765) --host (127.0.0.1) --data (./data) --open
  server.py               serveur HTTP (bibliothèque standard) : API JSON + fichiers statiques
  db.py                   SQLite : schéma, migrations, logique métier (statuts, progression)
  templating.py           variables {{…}} et analyse des tableaux de liens
  report.py               contenu des rapports PDF/Word et du tableau .docx
  docx_writer.py          écriture .docx en XML brut (paragraphes, tableaux, hyperliens, images)
  pdf_writer.py           écriture PDF (polices standard, mise en page, tableaux, liens, PNG/JPEG)
  static/                 frontend vanilla JS (index.html, style.css, api.js, app.js, fonts/)
data/delivery.db          base SQLite (créée au premier lancement, images incluses en BLOB)
tools/build_pyz.py        produit dist/checklist-livraison.pyz : toute l'app en un seul fichier
tools/build_demo.py       génère demo.html autonome (mock-api.js à la place d'api.js)
tools/build_release.py    assets de release dans dist/ (.pyz, .zip + INSTALLATION.md, SHA256SUMS.txt)
tools/snapshot_schema.py  fige une base d'exemple de la version de schéma courante (tests/fixtures)
.github/workflows/release.yml  version changée sur main (ou tag vX.Y.Z) : tests Python 3.8/3.12 puis release GitHub
CHANGELOG.md              notes de chaque version (source des notes de release)
tests/test_app.py         tests d'API bout en bout (python -m unittest discover tests)
```

Choix :
- **Zéro dépendance (E14)** : uniquement la bibliothèque standard de Python ≥ 3.8 (`http.server`,
  `sqlite3`, `zipfile`, `zlib`). Pas de pip, pas de venv, pas d'accès réseau, polices embarquées.
  Ne jamais ajouter de paquet tiers : l'environnement cible ne peut pas les installer.
- **Distribution** : soit le dossier (`python launch.py`), soit un fichier unique
  `checklist-livraison.pyz` (`python checklist-livraison.pyz`) ; les données vont dans `data/` à côté.
  Les fichiers statiques sont lus via `pkgutil.get_data`, ce qui marche dans les deux cas.
- **Word** : `.docx` écrit à la main (zip + WordprocessingML) : titres, tableaux à bordures, en-têtes
  répétés, hyperliens externes, images PNG/JPEG/GIF en ligne.
- **PDF** : écrit à la main (PDF 1.4) avec les polices standard Helvetica/Courier (encodage WinAnsi :
  les caractères hors cp1252 deviennent `?`), césure par métriques AFM, tableaux avec en-têtes
  répétés, liens cliquables, pied de page « page n/N ». Images : JPEG intégré tel quel ; PNG sans
  transparence transmis tel quel (prédicteur PNG du PDF) ; PNG avec transparence décodé en Python
  (≈ 1 à 4 s pour une capture Full HD, résultat mis en cache en mémoire).
- **Images en BLOB dans SQLite** : un seul fichier à sauvegarder (`data/delivery.db`).
  Limite 15 Mo par image ; le serveur n'accepte que PNG et JPEG, le navigateur convertit les
  autres formats (GIF, WebP, BMP…) en PNG avant l'envoi.
- **Écoute sur 127.0.0.1** par défaut (usage local, pas d'authentification).
- Variables d'environnement : `DELIVERY_PORT`, `DELIVERY_HOST`, `DELIVERY_DATA`.
- Polices IBM Plex (licence OFL) embarquées dans `static/fonts/` (sous-ensemble latin, ~150 Ko).

### 3.1 Schéma (version 3)

- `settings(key, value)` — `schema_version`, `default_variables` (JSON).
- `template_tasks(id, position, title, description, commands JSON, link_tables JSON, weight, estimated_minutes,
  created_at, updated_at)` + colonnes historiques `command`, `table_spec` (v1/v2, conservées mais inutilisées)
- `deliveries(id, version, name, variables JSON, status, created_at, completed_at)`
- `delivery_tasks(id, delivery_id→deliveries, template_task_id→template_tasks, position, title,
  description, commands JSON, link_tables JSON, weight, estimated_minutes, status, elapsed_seconds, running_since,
  started_at, completed_at)`
- `comments(id, delivery_task_id, body, created_at)`
- `images(id, delivery_task_id, filename, mime, size, data BLOB, created_at)`

Horodatages en UTC ISO-8601 (`2026-10-20T15:47:40Z`). Suppressions en cascade.
### 3.2 Compatibilité des bases (procédure obligatoire)

La version du schéma est stockée dans `settings.schema_version`. Au démarrage (`Database._migrate`) :

| Base trouvée | Comportement |
|--------------|--------------|
| absente / vide | création directe au dernier schéma (`SCHEMA`) + tâches d'exemple |
| même version | rien |
| plus ancienne | **copie de sauvegarde** `delivery.db.vN-AAAAMMJJ-HHMMSS.bak` à côté de la base, puis toutes les étapes `MIGRATIONS[N+1..]` dans **une seule transaction** (en cas d'erreur : rollback, base intacte) |
| plus récente | **refus de démarrer** avec un message clair, base non modifiée (une vieille app ne doit jamais toucher une base récente) |

Historique : v1 → v2 ajoute `table_spec` aux deux tables de tâches ; v2 → v3 ajoute `commands` et
`link_tables` (listes JSON) et y reprend l'ancienne commande et l'ancien tableau de chaque tâche.
L'API n'expose plus `command` / `table_spec`.

Pour toute évolution qui touche la base :

1. **Avant** de modifier le schéma, vérifier que `tests/fixtures/schema_v<actuelle>.sql` existe
   (sinon : `python tools/snapshot_schema.py`). Ces fichiers sont de vraies bases d'exemple produites
   par chaque version publiée ; ne jamais les modifier ni les supprimer.
2. Modifier `SCHEMA` (pour les nouvelles bases) **et** ajouter l'étape `MIGRATIONS[n+1]` (pour les
   anciennes). Ne jamais modifier une étape déjà publiée.
3. Règles de sûreté : uniquement des changements additifs (nouvelle table, nouvelle colonne avec
   `DEFAULT`) ; pas de renommage ni suppression de colonne (l'ancienne colonne reste, simplement
   ignorée) ; si une donnée doit être transformée, le faire en SQL dans l'étape de migration.
4. `python -m unittest discover tests` : `CompatibilityTest` charge chaque fixture, la migre, vérifie
   que le schéma obtenu est identique à celui d'une base neuve (attrape l'oubli d'une migration), que
   rien n'est perdu (comptes, commentaires, images), et que l'app fonctionne dessus (rapports, chrono).
5. Une fois la version publiée : `python tools/snapshot_schema.py` pour figer la nouvelle version,
   puis commit de la fixture (le test `test_every_version_has_a_fixture` le rappelle).

Côté utilisateur : garder `data/` lors d'une mise à jour (remplacer seulement l'app ou le `.pyz`) ;
la sauvegarde `.bak` permet de revenir en arrière avec l'ancienne version de l'app.

### 3.3 API

| Méthode | Route | Rôle |
|---------|-------|------|
| GET/PUT | `/api/settings` | variables par défaut |
| GET/POST | `/api/tasks` | modèle : liste / ajout |
| PUT/DELETE | `/api/tasks/{id}` | modèle : modifier / supprimer |
| POST | `/api/tasks/reorder` | `{ids:[…]}` |
| GET/POST | `/api/deliveries` | historique / créer (copie du modèle) |
| GET/PUT/DELETE | `/api/deliveries/{id}` | détail / version, nom, variables, statut / supprimer |
| POST | `/api/deliveries/{id}/tasks` | ajouter une tâche (`add_to_template` optionnel) |
| POST | `/api/deliveries/{id}/reorder` | réordonner |
| GET | `/api/deliveries/{id}/report.pdf` · `.docx` | rapport |
| PUT/DELETE | `/api/delivery-tasks/{id}` | modifier / retirer |
| GET | `/api/delivery-tasks/{id}/tables.docx` | tous les tableaux de la tâche, titrés, en .docx (`table.docx` : alias) |
| GET | `/api/delivery-tasks/{id}/tables/{n}.docx` | le n-ième tableau seul (à partir de 0) |
| POST | `/api/delivery-tasks/{id}/action` | `{action: start|pause|done|skip|reopen|reset}` |
| POST | `/api/delivery-tasks/{id}/comments` | `{body}` |
| POST | `/api/delivery-tasks/{id}/images` | corps brut, `Content-Type` PNG/JPEG, en-tête `X-Filename` |
| GET/DELETE | `/api/images/{id}` | image / suppression |
| DELETE | `/api/comments/{id}` | suppression |

Les mutations d'une livraison renvoient la livraison complète (l'UI se re-rend avec).

## 4. Interface

- Barre latérale : nouvelle livraison, modèle de tâches, historique (version, nom, date, % ou « Clôturée »).
- Vue livraison : en-tête (version, nom, exports PDF/Word, clôturer, menu), puces de variables,
  carte de progression, liste des tâches, ajout de tâche.
- Carte de tâche : bouton rond de validation, titre, statut, poids, estimé, chrono, Démarrer/Pause,
  Valider, menu (modifier, non applicable, monter/descendre, remise à zéro, retirer), replier/déplier.
  Corps : description, blocs de commande libellés avec bouton Copier chacun, tableaux pour Word
  (Copier pour Word / .docx par tableau, ou tous), captures (miniatures → visionneuse
  avec flèches/Échap), commentaires (Ctrl+Entrée pour publier, Ctrl+V pour coller une capture).
- Tâches validées repliées par défaut (dépliables) ; tâches ouvertes dépliées (repliables).
- Vue modèle : liste ordonnable, ajout/modification/suppression, aide sur les variables,
  variables par défaut.
- Thème clair/sombre automatique, responsive jusqu'à ~400 px.

## 5. Rapport (PDF / Word)

Titre, statut, dates, progression, compteurs, temps passé/estimé, variables ; tableau de synthèse
(tâche, statut, estimé, passé) ; détail par tâche : méta (statut, poids, temps, dates),
description et commandes **résolues**, tableau de liens, commentaires horodatés, images.

## 6. Pistes d'évolution

- Plusieurs modèles (ex. « livraison majeure » vs « correctif ») choisis à la création.
- Glisser-déposer pour réordonner.
- Tâches conditionnelles / dépendances entre tâches.
- Exécution directe des commandes depuis l'app (volontairement exclu pour l'instant : sécurité).
- Export/import du modèle en JSON ; sauvegarde automatique de la base.
- Multi-utilisateur (auteur des commentaires, authentification).

## 7. Journal

- **v1.0 (2026-10-20)** — Première version : modèle, livraisons historisées, variables, chronos,
  progression pondérée, commentaires, images, export PDF/Word, lanceurs, tests, démo autonome.
- **v1.1 (2026-10-20)** — Tableaux de liens pour Word par tâche (E13). Suppression de toutes les
  dépendances (E14) : générateurs PDF et .docx maison, polices embarquées, `launch.py`, archive
  `.pyz` unique, migration de schéma v2. Les GIF/WebP sont convertis en PNG par le navigateur.
- Version de l'application : `delivery_app.__version__` (doit correspondre au tag `vX.Y.Z` et à une
  section de `CHANGELOG.md`, vérifié par le workflow de release).

- **v1.2 (2026-10-20)** — Compatibilité des bases : migrations transactionnelles, sauvegarde
  automatique avant migration, refus d'une base plus récente, fixtures v1/v2 et tests de compatibilité.
- **v1.3 (2026-10-20)** — Plusieurs blocs de commande et plusieurs tableaux Word par tâche (E15, E16),
  schéma v3.
