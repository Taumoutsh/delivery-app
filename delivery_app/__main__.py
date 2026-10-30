"""Entry point: python -m delivery_app [--port 8765] [--data DIR] [--open] [--config FILE]

Also used by launch.py and by the single-file checklist-livraison.pyz build.

Options come, by priority, from the command line, the DELIVERY_* environment variables, the
checklist-livraison.ini file next to the app (or --config FILE), then the defaults. Several
instances can run side by side, each with its own port and its own data folder: a data folder
is locked by the instance using it.
"""

import argparse
import configparser
import json
import os
import socket
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .db import Database, SchemaTooNew
from .server import make_server

CONFIG_NAME = "checklist-livraison.ini"
DEFAULT_PORT = 8765
TRUE, FALSE = {"1", "oui", "yes", "true", "on", "vrai"}, {"0", "non", "no", "false", "off", "faux"}


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


class ConfigError(Exception):
    pass


def _yes_no(value, key, source):
    v = str(value).strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    raise ConfigError(f"{source} : « {key} = {value} » doit valoir oui ou non.")


def read_config(path):
    """Settings of an INI file ([checklist] section, or no section at all), relative paths resolved
    against the file's folder."""
    parser = configparser.ConfigParser()
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"Fichier de configuration illisible : {path} ({exc}).")
    try:
        parser.read_string(text if text.lstrip().startswith("[") else "[checklist]\n" + text)
    except configparser.Error as exc:
        raise ConfigError(f"{path} : {exc}")
    section = parser["checklist"] if parser.has_section("checklist") else {}
    out = {}
    for key, value in section.items():
        if key == "port":
            try:
                out["port"] = int(value)
            except ValueError:
                raise ConfigError(f"{path} : « port = {value} » doit être un nombre.")
        elif key == "data":
            data = Path(value).expanduser()
            out["data"] = str(data if data.is_absolute() else Path(path).parent / data)
        elif key in ("host", "hote", "hôte"):
            out["host"] = value
        elif key == "navigateur":
            out["open"] = _yes_no(value, key, path)
        elif key == "programmes":
            out["no_launch"] = not _yes_no(value, key, path)
        else:
            raise ConfigError(f"{path} : option inconnue « {key} » (port, data, navigateur, programmes, host).")
    return out


def load_options(argv=None, env=None, home=None):
    """Effective options: command line > DELIVERY_* variables > configuration file > defaults."""
    env = os.environ if env is None else env
    home = app_home() if home is None else Path(home)
    parser = argparse.ArgumentParser(description="Checklist de livraison")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, help=f"port d'écoute (défaut : {DEFAULT_PORT})")
    parser.add_argument("--data", help="dossier de la base et des vidéos (défaut : ./data)")
    parser.add_argument("--config", help=f"fichier de configuration (défaut : {CONFIG_NAME} à côté de l'app)")
    parser.add_argument("--open", action="store_true", default=None, help="ouvrir le navigateur au démarrage")
    parser.add_argument("--no-browser", dest="open", action="store_false", help="ne pas ouvrir le navigateur")
    parser.add_argument("--auto-open", action="store_true", help=argparse.SUPPRESS)  # set by the launchers
    parser.add_argument("--no-launch", action="store_true", default=None,
                        help="désactiver le lancement de programmes depuis les tâches")
    parser.add_argument("--version", action="version", version=f"Checklist Livraison {__version__}")
    args = parser.parse_args(argv)

    config_path = Path(args.config) if args.config else home / CONFIG_NAME
    if args.config and not config_path.is_file():
        raise ConfigError(f"Fichier de configuration introuvable : {config_path}")
    config = read_config(config_path) if config_path.is_file() else {}

    def pick(cli, env_key, conf_key, default, convert=str):
        if cli is not None:
            return cli
        if env.get(env_key):
            try:
                return convert(env[env_key])
            except ValueError:
                raise ConfigError(f"Variable {env_key}={env[env_key]} invalide.")
        return config.get(conf_key, default)

    port = pick(args.port, "DELIVERY_PORT", "port", DEFAULT_PORT, int)
    if not 0 < port < 65536:
        raise ConfigError(f"Port {port} invalide : choisissez un nombre entre 1 et 65535 (par exemple 8766).")
    return argparse.Namespace(
        host=pick(args.host, "DELIVERY_HOST", "host", "127.0.0.1"),
        port=port,
        data=Path(pick(args.data, "DELIVERY_DATA", "data", str(home / "data"))).expanduser().resolve(),
        open=args.open if args.open is not None else config.get("open", args.auto_open),
        no_launch=args.no_launch if args.no_launch is not None
        else (env.get("DELIVERY_NO_LAUNCH") == "1" or config.get("no_launch", False)),
        config=config_path if config else None,
    )


def port_is_free(host, port):
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def free_port(host, after):
    """First free port after `after` (to suggest one), or None."""
    return next((p for p in range(after + 1, min(after + 50, 65535)) if port_is_free(host, p)), None)


def busy_port_message(host, port):
    suggestion = free_port(host, port) or port + 1
    return (f"Le port {port} est déjà utilisé (par une autre instance ou une autre application).\n"
            f"Choisissez-en un autre : --port {suggestion}, ou « port = {suggestion} » dans {CONFIG_NAME}.")


class DataFolderInUse(Exception):
    pass


def lock_data_dir(data_dir, info):
    """Lock the data folder for this instance (released when the process ends, even on a crash).

    Raises DataFolderInUse, with the other instance's address when known."""
    lock_path = Path(data_dir) / ".instance.lock"
    f = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)  # byte 0 only: the details stay readable
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.seek(1)
        try:
            other = json.loads(f.read().decode("utf-8") or "{}")
        except ValueError:
            other = {}
        f.close()
        where = f" par l'instance {other['url']}" if other.get("url") else " par une autre instance"
        raise DataFolderInUse(f"Le dossier de données {data_dir} est déjà utilisé{where}.")
    f.seek(1)
    f.truncate()
    f.write(json.dumps(info).encode("utf-8"))
    f.flush()
    return f  # keep it open for the lifetime of the process


def main(argv=None):
    try:
        opts = load_options(argv)
    except ConfigError as exc:
        raise SystemExit(str(exc))
    if not port_is_free(opts.host, opts.port):  # before touching any data folder
        raise SystemExit(busy_port_message(opts.host, opts.port))
    data_dir = opts.data
    data_dir.mkdir(parents=True, exist_ok=True)
    url = f"http://{'localhost' if opts.host in ('127.0.0.1', '0.0.0.0') else opts.host}:{opts.port}/"
    try:
        lock = lock_data_dir(data_dir, {"url": url, "pid": os.getpid()})  # noqa: F841 (held until exit)
    except DataFolderInUse as exc:
        port = free_port(opts.host, opts.port) or opts.port + 1
        raise SystemExit(f"{exc}\nPour une deuxième instance, donnez-lui son propre dossier et son port, par exemple :\n"
                         f"  python checklist-livraison.pyz --port {port} --data data-{port}")
    try:
        db = Database(data_dir / "delivery.db")
    except SchemaTooNew as exc:
        raise SystemExit(str(exc))
    if db.backup_path:
        print(f"Base mise à jour ; sauvegarde de l'ancienne : {db.backup_path}")
    if db.compacted_bytes:
        print(f"Base compactée : {db.compacted_bytes / 1024 / 1024:.1f} Mo libérés.")
    try:
        server = make_server(db, opts.host, opts.port, allow_launch=not opts.no_launch,
                             instance={"url": url, "port": opts.port, "data": str(data_dir)})
    except OSError:  # taken in the meantime
        raise SystemExit(busy_port_message(opts.host, opts.port))
    print(f"Checklist de livraison {__version__} : {url}")
    print(f"Base de données        : {data_dir / 'delivery.db'}")
    if opts.config:
        print(f"Configuration          : {opts.config}")
    print("Ctrl+C pour arrêter.", flush=True)
    if opts.open:
        threading.Timer(0.6, open_browser, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
