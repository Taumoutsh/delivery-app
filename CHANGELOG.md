# Journal des versions

Chaque section `## X.Y.Z` sert de notes de release (lue par `tools/build_release.py`).
La version de l'application est dans `delivery_app/__init__.py`.

## 1.17.0 — 2026-10-30

- **Plusieurs instances en parallèle** : chacune avec son port et son dossier de données, par
  exemple `python checklist-livraison.pyz --port 8766 --data data-recette`.
- **Fichier de configuration** `checklist-livraison.ini` à côté de l'app (`port`, `data`,
  `navigateur`, `programmes`), pratique quand on lance l'app par un double-clic ; `--config FICHIER`
  pour un fichier par instance. Un exemple commenté est fourni dans la release.
- Sécurité des données : deux instances ne peuvent plus utiliser le même dossier de données ; la
  seconde refuse de démarrer et indique quelle instance l'utilise.
- Port déjà pris : message clair avec un port libre proposé, sans rien créer.
- Le port et le dossier de données s'affichent en bas de la barre latérale et dans « Application ».
- Aucun changement de format de base.

## 1.16.1 — 2026-10-29

- Correctif : dans la fenêtre de modification d'une tâche, la case « Tâche d'attente » est de nouveau
  à gauche de son libellé (elle s'affichait au-dessus).

## 1.16.0 — 2026-10-29

- **Tâche d'attente (cloche)** : un bouton cloche sur chaque tâche (dans la livraison, dans le
  modèle, et une case dans l'éditeur). Quand le chrono d'une tâche d'attente en cours atteint son
  temps estimé, la tâche clignote en rouge, la cloche s'agite, un bandeau « Attente terminée »
  s'affiche en haut de l'écran et le titre de l'onglet clignote, jusqu'au clic sur « J'ai vu ».
  Pratique pour attendre la fin d'un déploiement, d'un build ou d'une validation.
- **Logo de l'application** : encart en haut à gauche pour charger un PNG (clic ou
  glisser-déposer). Il s'affiche au-dessus du nom de l'application et dans l'onglet du navigateur ;
  « × » pour le retirer.
- Format de base v8 (mise à jour automatique avec sauvegarde `.bak`).

## 1.15.0 — 2026-10-29

- **Activer / désactiver des tâches du modèle** : un interrupteur à gauche de chaque tâche du
  modèle. Une tâche désactivée reste dans le modèle (grisée, avec tout son contenu) mais n'est plus
  copiée dans les nouvelles livraisons. Toutes les tâches sont activées par défaut.
- Le nombre de tâches et le temps estimé du modèle ne comptent que les tâches activées ; la
  fenêtre « Nouvelle livraison » indique combien de tâches seront copiées.
- Les livraisons existantes ne changent pas.
- Format de base v7 (mise à jour automatique avec sauvegarde `.bak`).

## 1.14.0 — 2026-10-21

- **Vidéos hors de la base** : elles sont rangées dans le dossier `data/media/`, à côté de la base.
  La base reste légère, les vidéos se lisent directement depuis le disque, et la limite passe de
  200 Mo à **2 Go** par vidéo (l'envoi n'est plus chargé en mémoire).
- Les vidéos déjà dans la base sont déplacées automatiquement dans `data/media/` au premier
  démarrage, puis la base est compactée. La sauvegarde `.bak` habituelle est faite avant.
- Une même vidéo envoyée plusieurs fois n'est stockée qu'une fois ; une vidéo plus utilisée par
  aucune tâche est supprimée par le ménage, fichier compris.
- Les images restent dans la base (elles sont intégrées aux rapports).
- **Sauvegarde** : copier tout le dossier `data/` (base + `media/`).
- Format de base v6 (mise à jour automatique).

## 1.13.0 — 2026-10-21

- **Chronos enchaînés** : le chrono de la première tâche démarre à la création de la livraison.
  Quand une tâche est validée ou marquée non applicable, le chrono de la tâche suivante démarre,
  et elle s'ouvre à l'écran. Rien ne démarre si un autre chrono tourne déjà.
- Désactivable : fenêtre « Application » → case « Enchaîner les chronos ».
- Aucun changement de format de base.

## 1.12.0 — 2026-10-21

- **Ménage de la base** : fenêtre « Application » (clic sur le titre ou la version) → section
  « Stockage ». Elle montre la taille de la base, ce qu'elle contient et ce qui peut être libéré.
  Le bouton « Faire le ménage » supprime les images et vidéos plus utilisées par aucune tâche et
  les données orphelines d'anciennes versions, puis **compacte le fichier**. On peut aussi supprimer
  les sauvegardes `.bak` faites avant les mises à jour de format.
- Le fichier se compacte aussi **automatiquement au démarrage** quand plus d'un quart est de
  l'espace vide laissé par des suppressions.
- Le journal de la base ne garde plus la taille de la plus grosse vidéo envoyée.
- Les livraisons, leur historique et le modèle ne sont jamais touchés. Aucun changement de format.

## 1.11.0 — 2026-10-21

- **Listes à plusieurs niveaux** dans les notes : Tab sur une ligne de liste la passe au niveau
  suivant, Maj+Tab la remonte (aussi sur plusieurs lignes sélectionnées). Puces et numéros se
  mélangent librement ; la numérotation repart à 1 dans chaque sous-liste.
- Rendu imbriqué dans la livraison, et en retrait par niveau dans les rapports PDF et Word.
- En dehors d'une liste, Tab passe toujours au champ suivant.
- Aucun changement de format de base.

## 1.10.0 — 2026-10-21

- **Mise en forme des notes** : gras, italique, souligné, barré, listes à puces et listes
  numérotées. Barre de boutons au-dessus du texte (sur la sélection ; un second clic retire la
  mise en forme), raccourcis Ctrl+B / Ctrl+I / Ctrl+U, et Entrée qui prolonge une liste.
- Syntaxe lisible même en texte brut : `**gras**`, `*italique*`, `__souligné__`, `~~barré~~`,
  lignes `- ` et `1. `. Les notes existantes s'affichent comme avant (un `*` isolé, `rm *.log`
  ou `{{prev_version}}` ne sont pas transformés).
- Rendu identique dans la livraison et dans les rapports PDF et Word.
- Aucun changement de format de base.

## 1.9.5 — 2026-10-21

- Valider une tâche (bouton « Valider » ou coche) ou la marquer non applicable publie d'abord le
  commentaire en cours de saisie : il n'est plus laissé de côté quand la tâche se replie.

## 1.9.4 — 2026-10-21

- Élément « Programme » : le chemin et les arguments ne sont plus affichés à côté du bouton
  « Lancer » ; la ligne de lancement complète apparaît au survol du bouton. Les rapports PDF/Word
  la citent toujours.

## 1.9.3 — 2026-10-21

- « Copier pour Word » : la copie passe désormais par l'événement de copie natif du navigateur, avec
  un document HTML complet, la forme que Word reconnaît le mieux. Les liens sont collés comme de vrais
  liens cliquables sur leur texte, au lieu de « texte (https://…) ». La copie en texte brut (Bloc-notes,
  messagerie…) garde l'adresse entre parenthèses.

## 1.9.2 — 2026-10-21

- Lisibilité : un fin séparateur sépare chaque élément d'une tâche (commande, lien, programme,
  tableau, médias, note). Il est en pointillés entre deux éléments du même type.

## 1.9.1 — 2026-10-21

- Élément « Lien » : l'adresse n'est plus affichée à côté du bouton ; seul le libellé reste visible.
  L'adresse complète apparaît au survol du bouton, et « Copier le lien » copie toujours l'adresse.
  Un lien sans libellé affiche toujours son adresse sur le bouton.

## 1.9.0 — 2026-10-21

- **Variables composées** : la valeur d'une variable peut utiliser d'autres variables, intégrées ou
  personnalisées, dans n'importe quel ordre et sur plusieurs niveaux. Exemple dans les variables par
  défaut : `url_ci = https://ci.example.com/{{env}}/{{version}}`.
- Les valeurs sont résolues à l'affichage : changer `env` dans une livraison met à jour `url_ci`.
  Valable partout : tâches, liens, programmes lancés, tableaux Word, rapports PDF/Word (le tableau
  des variables montre les valeurs résolues).
- Une variable qui en utilise une inconnue, vide ou en boucle est signalée en rouge, et
  l'avertissement de la tâche nomme la variable manquante.
- Aucun changement de format de base.

## 1.8.1 — 2026-10-21

- Correctif de l'erreur 415 à l'ajout d'une vidéo : tous les formats vidéo sont acceptés (AVI, MKV,
  WMV, MPEG…, plus seulement MP4/WebM/Ogg/MOV) ; quand le navigateur ne fournit pas le type du
  fichier, il est déduit de l'extension (ces fichiers étaient auparavant ignorés sans message).
- Un format que le navigateur ne sait pas lire est proposé en téléchargement dans la visionneuse.
- Message d'erreur explicite (nom du fichier, formats acceptés) ; déposer une vidéo dans les
  captures d'une livraison indique d'utiliser un élément « Images et vidéos ».

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
