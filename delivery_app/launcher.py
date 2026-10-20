"""Start a program of a "program" block on this machine (Windows, Linux, macOS).

The program is started detached: the app does not wait for it nor capture its output.
Executables and scripts are run with their arguments; any other file (document, folder,
shortcut…) is opened with the program the system associates with it.
"""

import os
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path

WINDOWS = sys.platform.startswith("win")
WINDOWS_EXECUTABLES = {".exe", ".bat", ".cmd", ".com"}


class LaunchError(Exception):
    pass


def split_args(args):
    if not args.strip():
        return []
    try:
        return shlex.split(args, posix=not WINDOWS)
    except ValueError as exc:
        raise LaunchError(f"Arguments invalides : {exc}")


def resolve(path):
    """Absolute path of the program: as given, or found in the PATH."""
    candidate = Path(os.path.expandvars(os.path.expanduser(path)))
    if candidate.exists():
        return candidate
    found = shutil.which(path)
    if found:
        return Path(found)
    raise LaunchError(f"Programme introuvable : {path}")


def build(program):
    """(argv or None, file to open with the system or None, working directory)."""
    target = resolve(program["path"])
    args = split_args(program.get("args", ""))
    cwd = program.get("cwd") or (str(target.parent) if target.is_file() else None)
    if cwd and not Path(cwd).is_dir():
        raise LaunchError(f"Dossier de travail introuvable : {cwd}")
    suffix = target.suffix.lower()
    if target.is_dir():
        return None, target, cwd
    if WINDOWS:
        if suffix in WINDOWS_EXECUTABLES:
            return [str(target), *args], None, cwd
        if suffix == ".ps1":
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(target), *args], None, cwd
        return (None, target, cwd) if not args else ([str(target), *args], None, cwd)
    if os.access(target, os.X_OK):
        return [str(target), *args], None, cwd
    if suffix in (".sh", ".py") and not args:
        return [("sh" if suffix == ".sh" else sys.executable), str(target)], None, cwd
    return None, target, cwd


def _reap(process):
    """Wait for the program in the background so it never lingers as a zombie process."""
    threading.Thread(target=process.wait, daemon=True).start()


def launch(program):
    """Start the program; returns a short description of what was started."""
    argv, document, cwd = build(program)
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    try:
        if argv:
            if WINDOWS:
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                _reap(subprocess.Popen(argv, cwd=cwd, creationflags=flags, **quiet))
            else:
                _reap(subprocess.Popen(argv, cwd=cwd, start_new_session=True, **quiet))
            return " ".join(argv)
        if WINDOWS:
            os.startfile(str(document))  # noqa: S606 — opens with the associated program
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            if not shutil.which(opener):
                raise LaunchError(f"Impossible d'ouvrir {document} : {opener} est absent.")
            _reap(subprocess.Popen([opener, str(document)], cwd=cwd, start_new_session=True, **quiet))
        return str(document)
    except OSError as exc:
        raise LaunchError(f"Lancement impossible : {exc}")
