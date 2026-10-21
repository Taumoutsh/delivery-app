# Journal des versions

Chaque section `## X.Y.Z` sert de notes de release (lue par `tools/build_release.py`).
La version de l'application est dans `delivery_app/__init__.py`.

## 1.8.0 — 2026-10-21

- Les variables (`{{version}}`, `{{env}}`…) sont aussi remplacées dans le **titre** des tâches : dans
  la livraison, dans les rapports PDF/Word (synthèse et détail) et dans le nom des fichiers `.docx`
  des tableaux. Une variable non renseignée dans un titre est signalée comme ailleurs.
- Le titre reste affiché tel qu'écrit dans le modèle et dans l'éditeur.

## 1.7.0 — 2026-10-20

- Une livraison clôturée est en **lecture seule** : plus de démarrage ni de validation de tâche, de
  modification, d'ajout ou de retrait de tâche, de commentaire ou de capture, ni de suppression de
  la livraison. On peut toujours la consulter, copier les commandes, lancer les programmes et
  exporter les rapports. Le bouton « Rouvrir » la rend de nouveau modifiable.
- Clôturer une livraison met en pause les chronos encore en marche.
- Le serveur applique aussi la règle (réponse 409), pas seulement l'interface.

## 1.6.0 — 2026-10-20

- Nom de l'application modifiable : cliquer sur le titre en haut de la barre latérale. Il est repris
  dans l'onglet du navigateur et en tête des rapports PDF/Word.
- Version de l'application affichée en bas de la barre latérale (avec le format de la base) et dans
  les rapports (« <nom> <version> » en en-tête et en pied de page) ; fenêtre « Application » avec
  ces informations.
- Aucun changement de format de base.

## 1.5.1 — 2026-10-20

- Correctif : dans la fenêtre de modification d'une tâche, seul le contenu défile désormais ; le titre
  et les boutons Annuler / Enregistrer restent visibles et la page derrière ne bouge plus.

## 1.5.0 — 2026-10-20

- **Éléments de tâche** : une tâche contient une liste d'éléments, tous facultatifs, ajoutés et
  triés librement (flèches ou glisser-déposer) : ligne de commande, **lien** (avec variables),
  **programme** (bouton « Lancer » : exécutable, script ou document ouvert sur votre poste),
  tableau pour Word, **images et vidéos**, note.
- Images et vidéos directement dans les tâches du modèle (bouton, glisser-déposer ou Ctrl+V) ;
  vidéos lisibles dans la visionneuse (200 Mo maximum).
- **Poids supprimé** : la progression est calculée sur le temps estimé de chaque tâche.
- Fenêtre de modification d'une tâche repensée : sections « Général » et « Contenu », cartes
  repliables, ajout par type, aide sur les variables.
- Sécurité : l'application refuse les requêtes venant d'autres sites ; option `--no-launch` pour
  désactiver le lancement de programmes.
- Format de base v5 : commandes, tableaux et captures de référence existants deviennent des éléments
  (mise à jour automatique avec sauvegarde `.bak`).

## 1.4.0 — 2026-10-20

- Captures de référence dans le modèle : on ajoute des captures à une tâche du modèle (bouton
  « Capture de référence » ou Ctrl+V sur la ligne). Chaque nouvelle livraison en reçoit une copie,
  affichée à part (« Captures de référence du modèle ») et reprise dans les rapports.
- Depuis une livraison, « → modèle » sur une capture l'ajoute au modèle pour les livraisons suivantes.
- Supprimer une capture du modèle ne touche pas aux livraisons existantes.
- Format de base v4 (mise à jour automatique avec sauvegarde `.bak`).

## 1.3.0 — 2026-10-20

- Plusieurs lignes de commande par tâche, chacune avec un libellé optionnel (Linux, Build, Rollback…)
  et son propre bouton Copier ; ordre modifiable.
- Plusieurs tableaux Word par tâche, chacun avec un titre : copie ou `.docx` d'un tableau, ou de tous
  les tableaux d'un coup (titres inclus).
- Format de base v3 : la commande et le tableau existants de chaque tâche sont repris automatiquement
  (sauvegarde `.bak` créée avant la mise à jour).

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
