#!/usr/bin/env sh
# Lance la checklist de livraison. Seul Python 3.8+ est requis (aucune dépendance).
# Options : --port 8765 --data ./data --no-browser
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || PY=python
exec "$PY" launch.py "$@"
