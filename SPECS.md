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

### 2.2 Statuts et chrono

`todo` → `running` ⇄ `paused` → `done` | `skipped` (non applicable).

- **Démarrer** : `running`, `running_since = now`, `started_at` fixé au premier démarrage.
- **Pause** : cumule `now - running_since` dans `elapsed_seconds`.
- **Valider** / **Non applicable** : cumule le temps, fixe `completed_at`, la tâche se replie.
- **Rouvrir** : revient à `paused` (ou `todo` si aucun temps passé).
- **Remettre à zéro** : statut `todo`, chrono à 0.
- Plusieurs tâches peuvent tourner en parallèle. Le temps est calculé côté serveur (UTC),
  l'interface rafraîchit l'affichage chaque seconde. Dépassement de l'estimé affiché en orange.

### 2.3 Progression

`progression = Σ poids(validées) / Σ poids(toutes sauf non applicables)`.
La barre est segmentée : un segment par tâche, largeur proportionnelle au poids, couleur selon
le statut. Affiche aussi tâches faites, poids, temps passé, estimé, reste estimé.

## 3. Architecture

```
run.sh / run.bat          lanceurs (venv + dépendances + ouverture navigateur)
requirements.txt          dépendances d'export uniquement (python-docx, reportlab, pillow)
delivery_app/
  __main__.py             CLI : --port (8765) --host (127.0.0.1) --data (./data) --open
  server.py               serveur HTTP (bibliothèque standard) : API JSON + fichiers statiques
  db.py                   SQLite : schéma, migrations, logique métier (statuts, progression)
  report.py               génération des rapports PDF et Word
  static/                 frontend vanilla JS (index.html, style.css, api.js, app.js)
data/delivery.db          base SQLite (créée au premier lancement, images incluses en BLOB)
tools/build_demo.py       génère demo.html autonome (mock-api.js à la place d'api.js)
tests/test_app.py         tests d'API bout en bout (python -m unittest discover tests)
```

Choix :
- **Aucune dépendance pour le serveur** (stdlib `http.server` + `sqlite3`) : l'app démarre même
  hors-ligne ; seul l'export PDF/Word requiert les paquets de `requirements.txt` (sinon HTTP 501
  avec message explicite).
- **Images en BLOB dans SQLite** : un seul fichier à sauvegarder (`data/delivery.db`).
  Limite 15 Mo par image ; PNG, JPEG, GIF, WebP.
- **Écoute sur 127.0.0.1** par défaut (usage local, pas d'authentification).
- Variables d'environnement : `DELIVERY_PORT`, `DELIVERY_HOST`, `DELIVERY_DATA`.
- Polices IBM Plex chargées depuis Google Fonts avec repli système (fonctionne hors-ligne).

### 3.1 Schéma (version 1)

- `settings(key, value)` — `schema_version`, `default_variables` (JSON).
- `template_tasks(id, position, title, description, command, weight, estimated_minutes, created_at, updated_at)`
- `deliveries(id, version, name, variables JSON, status, created_at, completed_at)`
- `delivery_tasks(id, delivery_id→deliveries, template_task_id→template_tasks, position, title,
  description, command, weight, estimated_minutes, status, elapsed_seconds, running_since,
  started_at, completed_at)`
- `comments(id, delivery_task_id, body, created_at)`
- `images(id, delivery_task_id, filename, mime, size, data BLOB, created_at)`

Horodatages en UTC ISO-8601 (`2026-10-20T15:47:40Z`). Suppressions en cascade.
Migrations : incrémenter `SCHEMA_VERSION` dans `db.py` et ajouter l'étape dans `_migrate()`.

### 3.2 API

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
| POST | `/api/delivery-tasks/{id}/action` | `{action: start|pause|done|skip|reopen|reset}` |
| POST | `/api/delivery-tasks/{id}/comments` | `{body}` |
| POST | `/api/delivery-tasks/{id}/images` | corps brut, `Content-Type` image, en-tête `X-Filename` |
| GET/DELETE | `/api/images/{id}` | image / suppression |
| DELETE | `/api/comments/{id}` | suppression |

Les mutations d'une livraison renvoient la livraison complète (l'UI se re-rend avec).

## 4. Interface

- Barre latérale : nouvelle livraison, modèle de tâches, historique (version, nom, date, % ou « Clôturée »).
- Vue livraison : en-tête (version, nom, exports PDF/Word, clôturer, menu), puces de variables,
  carte de progression, liste des tâches, ajout de tâche.
- Carte de tâche : bouton rond de validation, titre, statut, poids, estimé, chrono, Démarrer/Pause,
  Valider, menu (modifier, non applicable, monter/descendre, remise à zéro, retirer), replier/déplier.
  Corps : description, bloc de commande avec bouton Copier, captures (miniatures → visionneuse
  avec flèches/Échap), commentaires (Ctrl+Entrée pour publier, Ctrl+V pour coller une capture).
- Tâches validées repliées par défaut (dépliables) ; tâches ouvertes dépliées (repliables).
- Vue modèle : liste ordonnable, ajout/modification/suppression, aide sur les variables,
  variables par défaut.
- Thème clair/sombre automatique, responsive jusqu'à ~400 px.

## 5. Rapport (PDF / Word)

Titre, statut, dates, progression, compteurs, temps passé/estimé, variables ; tableau de synthèse
(tâche, statut, estimé, passé) ; détail par tâche : méta (statut, poids, temps, dates),
description et commandes **résolues**, commentaires horodatés, images.

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
