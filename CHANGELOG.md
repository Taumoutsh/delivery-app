# Journal des versions

Chaque section `## X.Y.Z` sert de notes de release (lue par `tools/build_release.py`).
La version de l'application est dans `delivery_app/__init__.py`.

## 1.2.0 — 2026-10-20

- Bases de données : mise à jour automatique sûre (sauvegarde `.bak` préalable, transaction unique,
  annulation en cas d'erreur) et refus d'ouvrir une base créée par une version plus récente.
- Tests de compatibilité sur de vraies bases des versions précédentes.
- `--version` en ligne de commande ; version affichée au démarrage.

## 1.1.0 — 2026-10-20

- Tableau de liens par tâche : « Copier pour Word » (tableau avec hyperliens collé directement dans
  Word), téléchargement en `.docx`, inclusion dans les rapports.
- Aucune dépendance : rapports PDF et Word générés en Python pur, polices embarquées, application
  livrée en un seul fichier `.pyz`. Seul Python 3.8+ est nécessaire.
- Les images GIF/WebP sont converties en PNG à l'ajout.

## 1.0.0 — 2026-10-20

- Première version : modèle de tâches, livraisons historisées, commandes adaptées à la version,
  progression pondérée, chronos, commentaires, captures, rapports PDF/Word.
