"""Entry point: python -m delivery_app [--port 8765] [--data DIR] [--open]

Also used by launch.py and by the single-file checklist-livraison.pyz build.
"""

import argparse
import os
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .db import Database, SchemaTooNew
from .server import make_server


def app_home():
    """Folder holding the app: the repository root, or the folder containing the .pyz file."""
    home = Path(__file__).resolve().parent.parent
    return home.parent if home.is_file() else home


DEFAULT_DATA = app_home() / "data"


def open_browser(url):
    try:
        webbrowser.open(url)
    except Exception:
        print(f"Ouvrez {url} dans votre navigateur.")


def main():
    parser = argparse.ArgumentParser(description="Checklist de livraison")
    parser.add_argument("--host", default=os.environ.get("DELIVERY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DELIVERY_PORT", "8765")))
    parser.add_argument("--data", default=os.environ.get("DELIVERY_DATA", str(DEFAULT_DATA)),
                        help="dossier contenant la base SQLite (défaut : ./data)")
    parser.add_argument("--open", action="store_true", help="ouvrir le navigateur au démarrage")
    parser.add_argument("--no-launch", action="store_true", default=os.environ.get("DELIVERY_NO_LAUNCH") == "1",
                        help="désactiver le lancement de programmes depuis les tâches")
    parser.add_argument("--version", action="version", version=f"Checklist Livraison {__version__}")
    args = parser.parse_args()

    data_dir = Path(args.data).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        db = Database(data_dir / "delivery.db")
    except SchemaTooNew as exc:
        raise SystemExit(str(exc))
    if db.backup_path:
        print(f"Base mise à jour ; sauvegarde de l'ancienne : {db.backup_path}")
    try:
        server = make_server(db, args.host, args.port, allow_launch=not args.no_launch)
    except OSError as exc:
        raise SystemExit(f"Impossible d'écouter sur le port {args.port} ({exc}). Essayez --port 8766.")
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}/"
    print(f"Checklist de livraison {__version__} : {url}")
    print(f"Base de données        : {data_dir / 'delivery.db'}")
    print("Ctrl+C pour arrêter.", flush=True)
    if args.open:
        threading.Timer(0.6, open_browser, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
