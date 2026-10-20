"""Entry point: python -m delivery_app [--port 8765] [--data DIR] [--open]"""

import argparse
import os
import threading
import webbrowser
from pathlib import Path

from .db import Database
from .server import make_server

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data"


def main():
    parser = argparse.ArgumentParser(description="Checklist de livraison")
    parser.add_argument("--host", default=os.environ.get("DELIVERY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DELIVERY_PORT", "8765")))
    parser.add_argument("--data", default=os.environ.get("DELIVERY_DATA", str(DEFAULT_DATA)),
                        help="dossier contenant la base SQLite (défaut : ./data)")
    parser.add_argument("--open", action="store_true", help="ouvrir le navigateur au démarrage")
    args = parser.parse_args()

    data_dir = Path(args.data).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(data_dir / "delivery.db")
    server = make_server(db, args.host, args.port)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}/"
    print(f"Checklist de livraison : {url}")
    print(f"Base de données        : {data_dir / 'delivery.db'}")
    print("Ctrl+C pour arrêter.")
    if args.open:
        threading.Timer(0.6, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
