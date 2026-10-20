#!/usr/bin/env sh
# Lance la checklist de livraison : crée l'environnement Python au premier lancement,
# installe les dépendances d'export puis ouvre le navigateur.
# Options transmises au serveur : --port 8765 --data ./data --host 127.0.0.1 (ou variables DELIVERY_PORT, DELIVERY_DATA)
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || PY=python
if [ ! -x .venv/bin/python ]; then
  echo "Création de l'environnement Python (.venv)..."
  "$PY" -m venv .venv
fi
if [ ! -f .venv/.deps-ok ] || [ requirements.txt -nt .venv/.deps-ok ]; then
  echo "Installation des dépendances d'export (PDF/Word)..."
  if .venv/bin/python -m pip install -q -r requirements.txt; then
    touch .venv/.deps-ok
  else
    echo "Attention : dépendances non installées, l'export PDF/Word sera indisponible."
  fi
fi
exec .venv/bin/python -m delivery_app --open "$@"
