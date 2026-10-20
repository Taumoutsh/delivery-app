# Checklist de livraison

Application web locale pour dérouler la checklist d'une livraison : tâches pondérées,
commandes copiables adaptées à la version, chronos, commentaires, captures, historique
et rapport PDF/Word.

## Lancer

```sh
./run.sh          # Linux / macOS
run.bat           # Windows (double-clic possible)
```

Prérequis : Python 3.9+. Au premier lancement, le script crée `.venv/` et installe les
dépendances d'export ; ensuite il démarre le serveur sur http://localhost:8765 et ouvre le
navigateur. La base est stockée dans `data/delivery.db` (à sauvegarder).

Options : `./run.sh --port 9000 --data /chemin/vers/dossier` (ou `DELIVERY_PORT`, `DELIVERY_DATA`).

Sans script : `python3 -m delivery_app --open` (l'export PDF/Word nécessite `pip install -r requirements.txt`).

## Développer

- Spécifications et décisions : [SPECS.md](SPECS.md)
- Tests : `python3 -m unittest discover tests`
- Démo autonome (sans serveur, données d'exemple) : `python3 tools/build_demo.py` → `demo.html`
