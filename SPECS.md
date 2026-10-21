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
| E4 | Lancement facile et autonome depuis un script, dans un dossier précis | ✅ `launch.py`, `.pyz` |
| E5 | Specs conservées dans un `.md` (ce fichier) | ✅ |
| E6 | Barre de progression ~~pondérée par un poids~~ pondérée par le **temps estimé** (v1.5) | ✅ |
| E7 | Valider une tâche la replie ; possibilité de la déplier | ✅ |
| E8 | Temps estimé + temps passé (chrono démarré par l'action « Démarrer ») | ✅ |
| E9 | Commentaires par tâche, pour chaque livraison | ✅ |
| E10 | Export d'un rapport de fin : PDF et Word | ✅ |
| E11 | Toutes les livraisons historisées et accessibles en base | ✅ |
| E12 | Une ou plusieurs images par tâche (miniature, agrandie à la demande) | ✅ |
| E13 | Tableau avec liens à insérer dans un document Word | ✅ copie riche + .docx |
| E14 | Tout embarquer : l'environnement cible n'exécute qu'un Python (pas de pip, pas d'internet) | ✅ stdlib uniquement |
| E15 | Plusieurs lignes de commande par tâche | ✅ |
| E16 | Plusieurs éléments Word (tableaux) par tâche | ✅ |
| E17 | Images dans une tâche du modèle | ✅ élément « Images et vidéos » |
| E18 | Images **et vidéos** insérées directement dans une tâche du modèle | ✅ v1.5 |
| E19 | Liens (pouvant contenir des variables) | ✅ v1.5 |
| E20 | Lancer un programme depuis l'application (chemin + nom) | ✅ v1.5, Windows/Linux/macOS |
| E21 | Tout est optionnel ; liens, notes, commandes, tableaux… ajoutés **et triés** dans la tâche | ✅ v1.5 |
| E22 | Architecture prête pour de nouveaux types d'éléments | ✅ registre d'éléments (§2.2) |
| E23 | Fenêtre de modification d'une tâche lisible | ✅ v1.5 (sections, cartes repliables) |
| E24 | Titre « Checklist Livraison » modifiable | ✅ v1.6 (réglage `app_title`) |
| E25 | Version de l'application visible | ✅ v1.6 (barre latérale, fenêtre « Application », rapports) |
| E26 | Livraison clôturée non modifiable, sauf si elle est rouverte | ✅ v1.7 (serveur + interface) |
| E27 | Variables par défaut pouvant utiliser d'autres variables | ✅ v1.9 (§2.1) |
| E28 | Notes : gras, italique, souligné, barré, listes à puces et numérotées | ✅ v1.10 (§2.3 bis) |
| E29 | Listes des notes à plusieurs niveaux (Tab) | ✅ v1.11 (§2.3 bis) |
| E30 | Faire le ménage dans la base (fichiers et données inutilisés), la garder compacte | ✅ v1.12 (§2.10) |

## 2. Concepts

- **Modèle de tâches** : la liste « maître » des tâches. Chaque nouvelle livraison en fait une
  **copie** (snapshot). Modifier le modèle ne réécrit jamais l'historique.
- **Livraison** : une version (ex. `2.4.0`), un nom optionnel, des variables personnalisées,
  un statut (`in_progress` / `done`), ses tâches.
- **Tâche** : titre, description, temps estimé, **liste ordonnée d'éléments** (§2.2). Dans une
  livraison s'y ajoutent statut, chrono, commentaires horodatés et captures prises pendant la
  livraison. Une tâche de livraison se modifie sans toucher le modèle (option « Appliquer aussi au
  modèle »).

### 2.1 Variables

Syntaxe `{{nom}}` dans le titre (depuis v1.8), la description et dans les champs texte des éléments (commande, lien,
programme, tableau, note, titres). Substitution à l'affichage, à la copie, au lancement et dans les
rapports. Une variable inconnue reste telle quelle et est signalée (soulignée en rouge).

| Variable | Valeur |
|----------|--------|
| `{{version}}` | version saisie |
| `{{major}}`, `{{minor}}`, `{{patch}}` | segments de la version (séparateurs `.`, `-`, `+`) |
| `{{date}}` | date de création de la livraison `AAAA-MM-JJ` |
| `{{name}}` | nom de la livraison |
| `{{prev_version}}` | pré-rempli avec la version de la livraison précédente |
| personnalisées | définies par livraison (`clé = valeur`), pré-remplies depuis les « variables par défaut » du modèle |

Les variables personnalisées surchargent les variables intégrées.

**Variables composées** (v1.9) : la valeur d'une variable peut utiliser d'autres variables, intégrées
ou personnalisées, à n'importe quelle profondeur et dans n'importe quel ordre
(`url_ci = https://ci.example.com/{{env}}/{{version}}`). La résolution se fait à l'affichage et à
l'export (`templating.resolve_variables`, reproduite dans `app.js`) : seules les valeurs saisies sont
stockées, donc changer `env` dans une livraison change aussi `url_ci`. Une référence inconnue, vide
ou en boucle (`a → b → a`) reste écrite telle quelle dans la valeur ; la variable est alors signalée
en rouge et la variable manquante apparaît dans l'avertissement de la tâche. Le tableau des variables
des rapports montre les valeurs résolues.

### 2.2 Éléments de tâche (registre extensible)

Une tâche porte `blocks`, liste ordonnée `[{id, type, …champs}]` (JSON en base). Tout est
facultatif : une tâche peut n'avoir aucun élément. Les éléments vides sont ignorés à l'enregistrement.

| Type | Champs | Affichage dans la livraison | Rapports |
|------|--------|-----------------------------|----------|
| `command` — Ligne de commande | `label`, `text` (multiligne) | bloc de code + **Copier** | libellé + code |
| `link` — Lien | `label`, `url` | bouton au libellé (adresse au survol, nouvel onglet) + **Copier le lien** | lien cliquable |
| `program` — Programme | `name`, `path`, `args`, `cwd` | bouton **Lancer** (ligne résolue au survol) | nom + ligne de lancement |
| `table` — Tableau pour Word | `title`, `spec` (§2.3) | tableau + **Copier pour Word** / **.docx** | tableau avec liens |
| `media` — Images et vidéos | `title`, `files` (ids de `media`) | miniatures → visionneuse (lecture vidéo) | images intégrées ; vidéos citées par nom |
| `note` — Note | `text` (mise en forme §2.3 bis) | encadré mis en forme | gras/italique/souligné/barré, listes |

**Ajouter un type** (prévu par l'architecture) :
1. `static/blocks.js` : une entrée dans `TYPES` (libellé, icône, champs vides, éditeur, lecture,
   résumé, textes à variables, affichage) et sa place dans `ORDER` ;
2. `delivery_app/blocks.py` : ses champs texte et le champ requis dans `TYPES` ;
3. `delivery_app/report.py` : son rendu dans `DOCX_RENDERERS` et `PDF_RENDERERS` (sinon il est
   absent des rapports) ;
4. si le type a besoin d'une action serveur (comme `program`), une route dédiée.
Aucune migration de base n'est nécessaire pour un nouveau type.

### 2.3 bis Mise en forme des notes (v1.10)

Le texte d'une note reste du texte brut stocké tel quel (aucun changement de schéma) ; une syntaxe
légère est interprétée à l'affichage et dans les rapports (`templating.parse_rich`, reproduite dans
`app.js`) :

| Saisie | Rendu |
|---|---|
| `**texte**` / `*texte*` / `__texte__` / `~~texte~~` | gras / italique / souligné / barré (combinables) |
| ligne `- `, `* ` ou `• ` | élément de liste à puces |
| ligne `1. ` ou `1) ` | élément de liste numérotée (commence au premier numéro saisi) |
| ligne de liste en retrait (une tabulation, ou deux espaces, par niveau) | sous-liste (v1.11), jusqu'à 6 niveaux ; puces et numéros mélangeables |
| ligne vide | nouveau paragraphe |
| `\*` | astérisque littéral |

- Un marqueur ne met en forme que s'il est refermé sur la même ligne, collé au texte (`**mot**`, pas
  `** mot **`) et pas au milieu d'un mot : `rm *.log`, `2 * 3`, `{{prev_version}}` restent intacts.
- Les variables sont remplacées après l'analyse : une valeur contenant `*` n'est pas interprétée.
- Sous-listes : un élément ne descend que d'un niveau sous la ligne qui précède (un retrait plus
  grand est ramené à ce niveau) ; la numérotation repart dans chaque sous-liste et continue dans
  une même liste ; un changement de type (puces ↔ numéros) à un niveau ouvre une nouvelle liste.
  `parse_rich` renvoie les éléments à plat avec leur niveau ; la page les imbrique en `ul`/`ol`.
- Éditeur : barre G / I / S / B / puces / numéros (sur la sélection, ou bascule si déjà appliqué),
  Ctrl+B / Ctrl+I / Ctrl+U, Entrée qui prolonge une liste (Entrée sur un élément vide la termine).
  Tab / Maj+Tab sur des lignes de liste : niveau suivant / précédent, avec renumérotation ; ailleurs,
  Tab garde son rôle (passer au champ suivant).
- Rapports : Word en runs `w:b`, `w:i`, `w:u`, `w:strike` et paragraphes en retrait avec puce ou
  numéro (retrait par niveau, puces • ◦ ▪) ; PDF avec Helvetica gras/oblique/gras-oblique, traits de
  soulignement et de barré, puces (• – ·) et numéros en retrait par niveau.

### 2.3 Tableaux pour Word

Syntaxe de `spec`, une rangée par ligne :

```
Élément | Lien
Notes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})
Tag Git | https://git.example.com/app/-/tags/v{{version}}
```

- Cellules séparées par `|` ; la 1re ligne donne les en-têtes ; `|` en début/fin et lignes `|---|` (style
  Markdown) ignorés ; rangées courtes complétées par des cellules vides.
- Liens : `[texte](url)` ou URL brute `http(s)://…` ; texte et liens peuvent se mélanger dans une cellule.
- **Copier pour Word** : presse-papiers HTML (styles en ligne : bordures, en-tête coloré, liens
  cliquables) + texte tabulé. Repli `execCommand('copy')` si l'API Clipboard est refusée.
- **Télécharger en .docx** : document contenant uniquement ce tableau. Avec plusieurs tableaux dans
  une tâche : **Copier tous les tableaux Word** / **Tous en .docx**, chacun précédé de son titre.
- Parseur en double : `templating.parse_table` (Python) et `parseTable` (`app.js`) — les garder alignés.

### 2.4 Programmes

- Le serveur tourne sur le poste de l'utilisateur : c'est lui qui lance le programme
  (`launcher.py`), détaché (l'app n'attend pas la fin et ne capture pas la sortie).
- `path` : chemin complet ou commande du PATH. Exécutables et scripts (`.exe`, `.bat`, `.cmd`,
  `.ps1` sous Windows ; fichiers exécutables, `.sh`, `.py` ailleurs) sont lancés avec `args`
  (découpés comme en shell) ; tout autre fichier ou dossier est ouvert avec l'application associée
  (`os.startfile`, `xdg-open`, `open`). `cwd` facultatif (dossier du programme par défaut).
- Variables résolues côté serveur au moment du lancement.
- **Sécurité** : le serveur ne lance que le programme d'un élément enregistré dans une tâche de
  livraison (route par identifiants, jamais de commande libre). Toute requête API qui modifie
  quelque chose doit porter l'en-tête `X-Checklist: 1` (une page d'un autre site ne peut pas
  l'ajouter sans pré-vérification CORS, jamais accordée) et l'en-tête `Host` doit être local
  (protection contre le DNS rebinding). Option `--no-launch` (ou `DELIVERY_NO_LAUNCH=1`) pour
  désactiver complètement le lancement.

### 2.5 Médias (images, vidéos)

- Images : PNG/JPEG (le navigateur convertit GIF, WebP, BMP… en PNG), 15 Mo maximum.
- Vidéos : tout type `video/*` (MP4, WebM, Ogg, MOV, AVI, MKV, WMV…), 200 Mo maximum ; si le
  navigateur n'envoie pas de type (ou `application/octet-stream`), il est déduit de l'extension.
  Lecture dans la visionneuse avec avance/recul (le serveur gère les requêtes `Range`) ; un format
  que le navigateur ne sait pas lire (AVI, WMV…) est proposé en téléchargement.
- Les captures d'une livraison restent des images ; un refus (415) nomme le fichier et les formats
  acceptés.
- Ajout dans l'éditeur : bouton, glisser-déposer sur l'élément, Ctrl+V dans l'élément. Le fichier
  est envoyé tout de suite (`POST /api/media`) et rattaché à l'enregistrement de la tâche.
- Fichiers **immuables et partagés** : une livraison créée depuis le modèle référence les mêmes
  fichiers (pas de duplication). Retirer un fichier du modèle ne touche pas aux livraisons.
  Au démarrage, les fichiers référencés par aucun élément depuis plus d'un jour sont supprimés (§2.10).
- Captures de livraison (preuves prises pendant la livraison) : distinctes, dans `images`, ajoutées
  par bouton ou Ctrl+V dans la tâche. « → modèle » (au survol) ajoute une capture à l'élément
  « Images et vidéos » de la tâche modèle d'origine (créé s'il n'existe pas).

### 2.6 Statuts et chrono

`todo` → `running` ⇄ `paused` → `done` | `skipped` (non applicable).

- **Démarrer** : `running`, `running_since = now`, `started_at` fixé au premier démarrage.
- **Pause** : cumule `now - running_since` dans `elapsed_seconds`.
- **Valider** / **Non applicable** : cumule le temps, fixe `completed_at`, la tâche se replie.
- **Rouvrir** : revient à `paused` (ou `todo` si aucun temps passé).
- **Remettre à zéro** : statut `todo`, chrono à 0.
- Plusieurs tâches peuvent tourner en parallèle. Le temps est calculé côté serveur (UTC),
  l'interface rafraîchit l'affichage chaque seconde. Dépassement de l'estimé affiché en orange.

### 2.7 Livraison clôturée (lecture seule)

- « Clôturer » (`status = done`) met en pause les tâches en cours puis fige la livraison.
- Tant qu'elle est clôturée, le serveur refuse toute modification avec **409** (« Livraison
  clôturée : rouvrez-la pour la modifier. ») : version, nom, variables, suppression de la livraison,
  ajout / modification / retrait / réordonnancement de tâche, actions de tâche (démarrer, valider…),
  commentaires et captures (ajout, suppression). Contrôle centralisé : `Database._ensure_open`.
- Restent possibles : consultation, déplier/replier, copie, lancement de programmes, exports PDF/Word
  et .docx, « → modèle » sur une capture (modifie le modèle, pas la livraison).
- « Rouvrir » (`PUT /api/deliveries/{id}` avec `{status: "in_progress"}`, seul changement accepté sur
  une livraison clôturée) rend la livraison de nouveau modifiable.
- L'interface masque les commandes de modification et affiche un bandeau « lecture seule ».

### 2.8 Nom et version de l'application

- **Nom** : réglage `app_title` (table `settings`, défaut « Checklist Livraison », 60 caractères
  maximum, espaces superflus retirés, vide = défaut). Modifié depuis la fenêtre « Application »
  (clic sur le titre de la barre latérale ou sur la version en bas). Affiché dans la barre latérale,
  l'onglet du navigateur, l'en-tête et le pied de page des rapports PDF, l'en-tête et les
  propriétés (auteur) des rapports Word.
- **Version** : `delivery_app.__version__` (source unique, voir §7), renvoyée par
  `GET /api/settings` (`app_version`, avec `schema_version`), affichée en bas de la barre latérale,
  dans la fenêtre « Application », dans les rapports et au démarrage du serveur (`--version`).

### 2.10 Stockage et ménage (v1.12)

Ce qui fait grossir la base n'est pas le texte des tâches (quelques Ko) mais les fichiers (images,
vidéos) et le fonctionnement de SQLite : une suppression libère des pages **dans** le fichier sans le
réduire, et le journal WAL garde la taille de la plus grosse écriture. Les suppressions sont
réelles : une tâche retirée du modèle ou d'une livraison n'est pas conservée (les tâches d'une
livraison sont la copie figée du modèle à sa création et font partie de son historique).

- Fenêtre « Application » → **Stockage** (`GET /api/storage`) : taille de la base et du journal,
  répartition (images et vidéos des tâches, captures des livraisons, texte des livraisons, modèle),
  ce que le ménage peut libérer, sauvegardes `.bak` des mises à jour de format.
- **Faire le ménage** (`POST /api/storage/cleanup`, `{"delete_backups": bool}`) :
  1. supprime les fichiers « Images et vidéos » référencés par aucun élément (modèle ou livraison),
     sauf ceux envoyés depuis moins de 10 minutes (un éditeur peut être ouvert) ;
  2. supprime les lignes orphelines (commentaires, captures, tâches dont le parent n'existe plus)
     et la table historique `template_images` (vidée par la migration v5) ;
  3. compacte le fichier (`wal_checkpoint(TRUNCATE)` + `VACUUM`) ;
  4. sur demande, supprime les sauvegardes `.bak` faites avant les mises à jour de format.
  Les livraisons, leur historique et le modèle ne sont jamais modifiés.
- **Automatique** : au démarrage, fichiers inutilisés depuis plus d'un jour et orphelins supprimés ;
  compactage si l'espace libre dépasse 25 % du fichier et 10 Mo (message « Base compactée »).
  `PRAGMA journal_size_limit` (8 Mo) empêche le journal de rester gros après un envoi de vidéo.

### 2.9 Progression

`progression = Σ estimé(validées) / Σ estimé(toutes sauf non applicables)`, une tâche sans
estimation comptant pour 1 minute (`db.weight_of`). La barre est segmentée : un segment par tâche,
largeur proportionnelle à l'estimé, couleur selon le statut. Affiche aussi tâches faites, temps
validé / estimé, temps passé, reste estimé.

## 3. Architecture

```
launch.py                 lanceur Python (ouvre le navigateur ; --no-browser pour l'éviter)
run.sh / run.bat          raccourcis vers launch.py
delivery_app/
  __main__.py             CLI : --port (8765) --host (127.0.0.1) --data (./data) --open --no-launch
  server.py               serveur HTTP (stdlib) : API JSON, fichiers statiques, protections (§2.4)
  db.py                   SQLite : schéma, migrations, logique métier (statuts, progression, médias)
  blocks.py               registre des types d'éléments côté serveur (validation)
  launcher.py             lancement des programmes (Windows, Linux, macOS)
  templating.py           variables {{…}} et analyse des tableaux pour Word
  report.py               rapports PDF/Word (un rendu par type d'élément) et tableaux .docx
  docx_writer.py          écriture .docx en XML brut (paragraphes, tableaux, hyperliens, images)
  pdf_writer.py           écriture PDF (polices standard, mise en page, tableaux, liens, PNG/JPEG)
  static/                 frontend vanilla JS : index.html, style.css, api.js, blocks.js (registre
                          des éléments), app.js, fonts/
data/delivery.db          base SQLite (créée au premier lancement, fichiers inclus en BLOB)
tools/build_pyz.py        produit dist/checklist-livraison.pyz : toute l'app en un seul fichier
tools/build_demo.py       génère demo.html autonome (mock-api.js à la place d'api.js)
tools/build_release.py    assets de release dans dist/ (.pyz, .zip + INSTALLATION.md, SHA256SUMS.txt)
tools/snapshot_schema.py  fige une base d'exemple de la version de schéma courante (tests/fixtures)
.github/workflows/release.yml  version changée sur main (ou tag vX.Y.Z) : tests Python 3.8/3.12 puis release GitHub
CHANGELOG.md              notes de chaque version (source des notes de release)
tests/test_app.py         tests d'API bout en bout, écrivains PDF/Word, compatibilité des bases
```

Choix :
- **Zéro dépendance (E14)** : uniquement la bibliothèque standard de Python ≥ 3.8. Pas de pip, pas
  de venv, pas d'accès réseau, polices embarquées. Ne jamais ajouter de paquet tiers.
- **Distribution** : soit le dossier (`python launch.py`), soit un fichier unique
  `checklist-livraison.pyz` ; les données vont dans `data/` à côté. Les fichiers statiques sont lus
  via `pkgutil.get_data`, ce qui marche dans les deux cas.
- **Word** : `.docx` écrit à la main (zip + WordprocessingML).
- **PDF** : écrit à la main (PDF 1.4, polices standard, encodage WinAnsi : les caractères hors
  cp1252 deviennent `?`). PNG avec transparence décodé en Python (≈ 1 à 4 s pour une capture
  Full HD, mis en cache en mémoire).
- **Fichiers en BLOB dans SQLite** : un seul fichier à sauvegarder (`data/delivery.db`).
- **Écoute sur 127.0.0.1** par défaut (usage local, pas d'authentification). Avec `--host <ip>`,
  cette adresse est ajoutée aux hôtes autorisés.
- Variables d'environnement : `DELIVERY_PORT`, `DELIVERY_HOST`, `DELIVERY_DATA`, `DELIVERY_NO_LAUNCH`.

### 3.1 Schéma (version 5)

- `settings(key, value)` — `schema_version`, `default_variables` (JSON), `app_title`.
- `template_tasks(id, position, title, description, blocks JSON, estimated_minutes, created_at,
  updated_at)` + colonnes historiques inutilisées : `command`, `table_spec`, `commands`,
  `link_tables`, `weight`.
- `deliveries(id, version, name, variables JSON, status, created_at, completed_at)`
- `delivery_tasks(id, delivery_id→deliveries, template_task_id→template_tasks, position, title,
  description, blocks JSON, estimated_minutes, status, elapsed_seconds, running_since, started_at,
  completed_at)` + mêmes colonnes historiques.
- `comments(id, delivery_task_id, body, created_at)`
- `images(id, delivery_task_id, filename, mime, size, data BLOB, created_at, reference)` — captures
  prises pendant la livraison (`reference` historique, toujours 0 depuis v5).
- `media(id, filename, mime, size, data BLOB, created_at)` — fichiers des éléments « Images et vidéos ».
- `template_images(…)` — historique (v4), vidé par la migration v5.

Horodatages en UTC ISO-8601 (`2026-10-20T15:47:40Z`). Suppressions en cascade.

### 3.2 Compatibilité des bases (procédure obligatoire)

La version du schéma est stockée dans `settings.schema_version`. Au démarrage (`Database._migrate`) :

| Base trouvée | Comportement |
|--------------|--------------|
| absente / vide | création directe au dernier schéma (`SCHEMA`) + tâches d'exemple |
| même version | rien |
| plus ancienne | **copie de sauvegarde** `delivery.db.vN-AAAAMMJJ-HHMMSS.bak` à côté de la base, puis toutes les étapes `MIGRATIONS[N+1..]` dans **une seule transaction** (en cas d'erreur : rollback, base intacte) |
| plus récente | **refus de démarrer** avec un message clair, base non modifiée |

Historique :
- v1 → v2 : `table_spec` sur les tâches.
- v2 → v3 : listes JSON `commands` / `link_tables`, reprise de la commande et du tableau existants.
- v3 → v4 : `template_images` et `images.reference` (captures de référence copiées dans les livraisons).
- v4 → v5 : colonne `blocks` et table `media`. Commandes et tableaux deviennent des éléments ;
  les captures de référence (modèle et copies en livraison) deviennent un élément « Images et
  vidéos » « Captures de référence », leurs fichiers passent dans `media`.

Pour toute évolution qui touche la base :

1. **Avant** de modifier le schéma, vérifier que `tests/fixtures/schema_v<actuelle>.sql` existe
   (sinon : `python tools/snapshot_schema.py`). Ces fichiers sont de vraies bases d'exemple produites
   par chaque version publiée ; ne jamais les modifier ni les supprimer.
2. Modifier `SCHEMA` (pour les nouvelles bases) **et** ajouter l'étape `MIGRATIONS[n+1]` (pour les
   anciennes). Ne jamais modifier une étape déjà publiée.
3. Règles de sûreté : uniquement des changements additifs (nouvelle table, nouvelle colonne avec
   `DEFAULT`) ; pas de renommage ni suppression de colonne (l'ancienne colonne reste, simplement
   ignorée) ; si une donnée doit être transformée, le faire dans l'étape de migration.
4. `python -m unittest discover tests` : `CompatibilityTest` charge chaque fixture, la migre, vérifie
   que le schéma obtenu est identique à celui d'une base neuve, que rien n'est perdu (comptes,
   commentaires, **tous les fichiers** quelle que soit leur table), et que l'app fonctionne dessus.
5. Une fois la version publiée : `python tools/snapshot_schema.py` pour figer la nouvelle version,
   puis commit de la fixture (le test `test_every_version_has_a_fixture` le rappelle).

Un **nouveau type d'élément** ne demande pas de migration (§2.2).

Côté utilisateur : garder `data/` lors d'une mise à jour (remplacer seulement l'app ou le `.pyz`) ;
la sauvegarde `.bak` permet de revenir en arrière avec l'ancienne version de l'app.

### 3.3 API

Toute requête qui modifie quelque chose doit porter `X-Checklist: 1` (§2.4).

| Méthode | Route | Rôle |
|---------|-------|------|
| GET/PUT | `/api/settings` | `default_variables`, `app_title` (PUT partiel : seules les clés envoyées changent) ; GET ajoute `app_version`, `schema_version` |
| GET | `/api/storage` | tailles, contenu, espace récupérable, sauvegardes (§2.10) |
| POST | `/api/storage/cleanup` | ménage + compactage ; `delete_backups` ; renvoie le nouvel état et `result` |
| GET/POST | `/api/tasks` | modèle : liste / ajout (`{title, description, estimated_minutes, blocks}`) |
| PUT/DELETE | `/api/tasks/{id}` | modèle : modifier / supprimer |
| POST | `/api/tasks/reorder` | `{ids:[…]}` |
| GET/POST | `/api/deliveries` | historique / créer (copie du modèle) |
| GET/PUT/DELETE | `/api/deliveries/{id}` | détail / version, nom, variables, statut / supprimer |
| POST | `/api/deliveries/{id}/tasks` | ajouter une tâche (`add_to_template` optionnel) |
| POST | `/api/deliveries/{id}/reorder` | réordonner |
| GET | `/api/deliveries/{id}/report.pdf` · `.docx` | rapport |
| PUT/DELETE | `/api/delivery-tasks/{id}` | modifier / retirer |
| POST | `/api/delivery-tasks/{id}/action` | `{action: start|pause|done|skip|reopen|reset}` |
| POST | `/api/delivery-tasks/{id}/blocks/{blockId}/launch` | lance le programme de l'élément |
| GET | `/api/delivery-tasks/{id}/tables.docx` | tous les tableaux Word de la tâche (`table.docx` : alias) |
| GET | `/api/delivery-tasks/{id}/tables/{blockId}.docx` | un tableau Word |
| POST | `/api/delivery-tasks/{id}/comments` | `{body}` |
| DELETE | `/api/comments/{id}` | suppression |
| POST | `/api/delivery-tasks/{id}/images` | capture de livraison (corps brut PNG/JPEG, en-tête `X-Filename`) |
| GET/DELETE | `/api/images/{id}` | capture / suppression |
| POST | `/api/images/{id}/to-template` | ajoute la capture à l'élément média de la tâche modèle |
| POST | `/api/media` | fichier d'un élément « Images et vidéos » (corps brut) → `{id, filename, mime, size, url}` |
| GET | `/api/media/{id}` | fichier (supporte `Range`) |

Les mutations d'une livraison renvoient la livraison complète (l'UI se re-rend avec).

## 4. Interface

- Barre latérale : nom de l'application (cliquable : fenêtre « Application »), nouvelle livraison,
  modèle de tâches, historique (version, nom, date, % ou « Clôturée »), en bas la version de
  l'application et du format de base.
- Vue livraison : en-tête (version, nom, exports PDF/Word, clôturer, menu), puces de variables,
  carte de progression, liste des tâches, ajout de tâche.
- Carte de tâche : validation, titre, statut, estimé, compteurs par type d'élément, chrono,
  Démarrer/Pause, Valider, menu (modifier, non applicable, monter/descendre, remise à zéro, retirer),
  replier/déplier. Corps : description, éléments dans leur ordre (titre de type affiché une fois par
  suite d'éléments du même type), captures de la livraison, commentaires (Ctrl+Entrée pour publier,
  Ctrl+V pour coller une capture ; un commentaire en cours de saisie est publié automatiquement quand
  on valide la tâche ou la marque non applicable).
- **Éditeur de tâche** (modèle et livraison) : fenêtre large, section « Général » (titre, temps
  estimé, description), section « Contenu » (cartes repliables avec type, résumé, ⠿ pour glisser,
  ↑ ↓, supprimer ; repliées par défaut au-delà de 3 éléments), boutons « Ajouter » par type, aide sur
  les variables repliable, pied de fenêtre fixe.
- Vue modèle : liste ordonnable, résumé des éléments de chaque tâche, temps estimé, aide sur les
  variables, variables par défaut.
- Thème clair/sombre automatique, responsive jusqu'à ~400 px.

## 5. Rapport (PDF / Word)

« <nom de l'application> <version> », titre, statut, dates, progression, compteurs, temps passé/estimé, variables ; tableau de synthèse
(tâche, statut, estimé, passé) ; détail par tâche : méta (statut, temps, dates), description,
éléments dans leur ordre avec variables **résolues** (rendu par type, §2.2), commentaires
horodatés, captures de la livraison.

## 6. Pistes d'évolution

- Plusieurs modèles (ex. « livraison majeure » vs « correctif ») choisis à la création.
- Nouveaux types d'éléments : case à cocher (sous-étapes), requête HTTP de vérification, fichier
  joint (PDF, archive)…
- Tâches conditionnelles / dépendances entre tâches.
- Export/import du modèle en JSON ; sauvegarde automatique de la base.
- Multi-utilisateur (auteur des commentaires, authentification).

## 7. Journal

Version de l'application : `delivery_app.__version__` (doit correspondre au tag `vX.Y.Z` et à une
section de `CHANGELOG.md`, vérifié par le workflow de release).

- **v1.0** — Première version : modèle, livraisons historisées, variables, chronos, progression
  pondérée, commentaires, images, export PDF/Word, lanceurs, tests, démo autonome.
- **v1.1** — Tableaux de liens pour Word (E13). Zéro dépendance (E14) : générateurs PDF et .docx
  maison, polices embarquées, `launch.py`, archive `.pyz`, schéma v2.
- **v1.2** — Compatibilité des bases : migrations transactionnelles, sauvegarde avant migration,
  refus d'une base plus récente, fixtures et tests de compatibilité.
- **v1.3** — Plusieurs commandes et plusieurs tableaux Word par tâche (E15, E16), schéma v3.
- **v1.4** — Captures de référence sur les tâches du modèle (E17), schéma v4.
- **v1.5** — Éléments de tâche typés et triables via un registre extensible (E21, E22) : liens
  (E19), programmes lançables (E20), images et vidéos (E18), notes ; poids supprimé, progression au
  temps estimé (E6) ; éditeur repensé (E23) ; protections contre les requêtes d'autres sites ;
  schéma v5.
- **v1.5.1** — Correctif : seul le contenu de la fenêtre de modification défile.
- **v1.6** — Nom de l'application modifiable (E24), version visible dans l'interface et les
  rapports (E25). Pas de changement de schéma.
- **v1.7** — Livraison clôturée en lecture seule jusqu'à sa réouverture (E26), clôture qui met les
  chronos en pause. Pas de changement de schéma.
- **v1.8** — Variables dans le titre des tâches (livraison, rapports, noms des .docx).
- **v1.8.1** — Correctif : toutes les vidéos acceptées (AVI, MKV, WMV…), type déduit de l'extension.
- **v1.9** — Variables composées : une variable peut utiliser d'autres variables (E27). Pas de changement de schéma.
- **v1.9.1** — Lien : adresse masquée à côté du bouton (visible au survol).
- **v1.9.2** — Séparateurs entre les éléments d'une tâche (pointillés entre éléments du même type).
- **v1.9.3** — « Copier pour Word » : copie par événement natif (HTML complet + texte brut), liens collés comme hyperliens.
- **v1.9.4** — Programme : chemin masqué à côté du bouton « Lancer » (visible au survol).
- **v1.9.5** — Commentaire en cours de saisie publié à la validation de la tâche.
- **v1.10** — Mise en forme des notes : gras, italique, souligné, barré, listes (E28). Pas de changement de schéma.
- **v1.11** — Listes à plusieurs niveaux dans les notes (Tab / Maj+Tab).
- **v1.12** — Stockage : état de la base, « Faire le ménage », compactage automatique, journal limité (E30).
