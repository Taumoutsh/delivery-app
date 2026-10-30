# Checklist de livraison

Application web locale pour dérouler la checklist d'une livraison. Chaque tâche contient des
éléments triables : commandes copiables adaptées à la version, liens, programmes à lancer,
tableaux à coller dans Word, images et vidéos, notes. Chronos, progression au temps estimé,
commentaires, captures, historique et rapport PDF/Word.

**Aucune dépendance** : seul Python 3.8+ est nécessaire (pas de pip, pas d'internet).

## Lancer

```sh
python launch.py                  # depuis ce dossier (ou ./run.sh, run.bat)
python checklist-livraison.pyz    # version fichier unique, voir ci-dessous
```

Le serveur démarre sur http://localhost:8765 et ouvre le navigateur. La base est stockée dans
`data/delivery.db` à côté de l'app, les vidéos dans `data/media/` : c'est le dossier `data/` entier
qu'il faut sauvegarder.

Options : `--port 9000`, `--data /chemin/vers/dossier`, `--no-browser`, `--no-launch` (désactive
le lancement de programmes), `--config FICHIER` — ou variables `DELIVERY_PORT`, `DELIVERY_DATA`,
`DELIVERY_NO_LAUNCH=1` — ou un fichier `checklist-livraison.ini` à côté de l'app (`port`, `data`,
`navigateur`, `programmes`). Priorité : ligne de commande, variables, fichier, valeurs par défaut.

**Deux instances en parallèle** : chacune avec son port et son dossier de données, par exemple
`python checklist-livraison.pyz --port 8766 --data data-recette` (ou `--config recette.ini`). Un
dossier de données est verrouillé par l'instance qui l'utilise : une seconde instance sur le même
dossier refuse de démarrer.

## Fichier unique

```sh
python tools/build_pyz.py         # → dist/checklist-livraison.pyz (~170 Ko)
```

Copiez ce seul fichier dans l'environnement cible et lancez-le avec `python`.

## Publier une version

1. Mettre à jour `__version__` dans `delivery_app/__init__.py` et ajouter la section dans `CHANGELOG.md`.
2. `python tools/build_release.py` : tests + `dist/` (`.pyz`, `.zip` avec guide d'installation, `SHA256SUMS.txt`).
3. Fusionner dans `main` : quand la version change, le workflow `.github/workflows/release.yml` teste
   sous Python 3.8 et 3.12 puis publie la release GitHub `vX.Y.Z` avec ces fichiers (un tag `vX.Y.Z`
   poussé à la main fonctionne aussi).

## Développer

- Spécifications et décisions : [SPECS.md](SPECS.md)
- Tests : `python -m unittest discover tests`
- Démo autonome (sans serveur, données d'exemple) : `python tools/build_demo.py` → `demo.html`
