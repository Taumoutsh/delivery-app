# Checklist de livraison

Application web locale pour dérouler la checklist d'une livraison : tâches pondérées,
commandes copiables adaptées à la version, chronos, commentaires, captures, tableaux de liens
à coller dans Word, historique et rapport PDF/Word.

**Aucune dépendance** : seul Python 3.8+ est nécessaire (pas de pip, pas d'internet).

## Lancer

```sh
python launch.py                  # depuis ce dossier (ou ./run.sh, run.bat)
python checklist-livraison.pyz    # version fichier unique, voir ci-dessous
```

Le serveur démarre sur http://localhost:8765 et ouvre le navigateur. La base est stockée dans
`data/delivery.db` à côté de l'app (c'est le seul fichier à sauvegarder).

Options : `--port 9000`, `--data /chemin/vers/dossier`, `--no-browser`
(ou variables `DELIVERY_PORT`, `DELIVERY_DATA`).

## Fichier unique

```sh
python tools/build_pyz.py         # → dist/checklist-livraison.pyz (~170 Ko)
```

Copiez ce seul fichier dans l'environnement cible et lancez-le avec `python`.

## Développer

- Spécifications et décisions : [SPECS.md](SPECS.md)
- Tests : `python -m unittest discover tests`
- Démo autonome (sans serveur, données d'exemple) : `python tools/build_demo.py` → `demo.html`
