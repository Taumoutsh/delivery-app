"""Lance la checklist de livraison : python launch.py [--port 8765] [--data DOSSIER] [--no-browser]

Aucune dépendance : seul Python 3.8+ est nécessaire.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from delivery_app.__main__ import main  # noqa: E402

if __name__ == "__main__":
    if "--no-browser" in sys.argv:
        sys.argv.remove("--no-browser")
    elif "--open" not in sys.argv:
        sys.argv.append("--open")
    main()
