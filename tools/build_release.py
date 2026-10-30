"""Build the release assets in dist/ (used locally and by .github/workflows/release.yml).

Usage: python tools/build_release.py [--skip-tests]

Produces, for version X.Y.Z (delivery_app.__version__):
  dist/checklist-livraison-X.Y.Z.pyz   the whole app in one file
  dist/checklist-livraison-X.Y.Z.zip   pyz + launchers + install guide + changelog
  dist/SHA256SUMS.txt                  checksums to verify the transfer
  dist/RELEASE_NOTES.md                this version's changelog section
"""

import hashlib
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT))

from delivery_app import __version__  # noqa: E402
from tools.build_pyz import build as build_pyz  # noqa: E402

INSTALL = """# Checklist Livraison {v} — installation

Prérequis : Python 3.8 ou plus récent. Aucune autre dépendance, aucun accès internet.

## Première installation

1. Copier `checklist-livraison.pyz` (et éventuellement `lancer.bat` / `lancer.sh`) dans un dossier, par
   exemple `C:\\outils\\checklist\\` ou `~/outils/checklist/`.
2. Lancer : `python checklist-livraison.pyz` (ou double-clic sur `lancer.bat`).
3. Le navigateur s'ouvre sur http://localhost:8765. La base est créée dans `data/` à côté du fichier
   (`data/delivery.db`, et les vidéos dans `data/media/`). Pour sauvegarder, copier tout le dossier `data/`.

Options : `--port 9000`, `--data CHEMIN`, `--no-browser`, `--config FICHIER`, `--version`, ou le
fichier `checklist-livraison.ini` à côté du `.pyz` (exemple fourni, tout est en commentaire).

## Plusieurs instances en parallèle

Chaque instance a **son port** et **son dossier de données** (deux instances ne peuvent pas partager
le même dossier : la seconde refuse de démarrer et le dit).

- En ligne de commande :
  `python checklist-livraison.pyz --port 8766 --data data-recette`
- Ou avec un fichier par instance, par exemple `recette.ini` :
  ```
  port = 8766
  data = data-recette
  ```
  puis `python checklist-livraison.pyz --config recette.ini`.
- Ou un dossier par instance, chacun avec son `.pyz` et son `checklist-livraison.ini`.

Le port et le dossier de chaque instance s'affichent en bas de la barre latérale et dans la fenêtre
« Application ». Si un port est déjà pris, l'application le dit et propose un port libre.

## Mise à jour

1. Arrêter l'application (Ctrl+C dans la console).
2. Remplacer **uniquement** `checklist-livraison.pyz`. Ne pas toucher au dossier `data/`.
3. Relancer. Si le format de la base a changé, elle est mise à jour automatiquement et une copie de
   l'ancienne est conservée dans `data/delivery.db.vN-….bak`.

Retour arrière : remettre l'ancien `.pyz` et, si la base avait été mise à jour, renommer le `.bak` en
`delivery.db`.

## Vérifier le fichier reçu

Comparer l'empreinte SHA-256 avec `SHA256SUMS.txt` :
- Windows : `certutil -hashfile checklist-livraison.pyz SHA256`
- Linux/macOS : `sha256sum checklist-livraison.pyz`
- Partout : `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" checklist-livraison.pyz`
"""

CONFIG_EXAMPLE = """# Configuration de la checklist de livraison (lue au démarrage, à côté du .pyz).
# Retirez le # devant une ligne pour l'activer. La ligne de commande reste prioritaire.

# Port d'écoute (une instance par port) :
# port = 8765

# Dossier de la base et des vidéos (relatif à ce fichier, ou chemin complet) :
# data = data

# Ouvrir le navigateur au démarrage (oui / non) :
# navigateur = oui

# Autoriser les éléments « Programme » à lancer des programmes (oui / non) :
# programmes = oui
"""

LANCER_BAT = """@echo off
rem Lance la checklist de livraison (Python 3.8+ requis).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 checklist-livraison.pyz %*) else (python checklist-livraison.pyz %*)
pause
"""

LANCER_SH = """#!/usr/bin/env sh
# Lance la checklist de livraison (Python 3.8+ requis).
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || PY=python
exec "$PY" checklist-livraison.pyz "$@"
"""


def release_notes():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(__version__)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md n'a pas de section « ## {__version__} ».")
    return m.group(1).strip() + "\n"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if "--skip-tests" not in sys.argv:
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT, check=True)
    notes = release_notes()
    DIST.mkdir(exist_ok=True)
    base = f"checklist-livraison-{__version__}"
    pyz = build_pyz(DIST / f"{base}.pyz")
    bundle = DIST / f"{base}.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(pyz, f"{base}/checklist-livraison.pyz")
        z.writestr(f"{base}/INSTALLATION.md", INSTALL.format(v=__version__))
        z.writestr(f"{base}/CHANGELOG.md", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        z.writestr(f"{base}/lancer.bat", LANCER_BAT.replace("\n", "\r\n"))
        z.writestr(f"{base}/checklist-livraison.ini", CONFIG_EXAMPLE.replace("\n", "\r\n"))
        info = zipfile.ZipInfo(f"{base}/lancer.sh")
        info.external_attr = 0o100755 << 16
        info.date_time = time.localtime()[:6]
        z.writestr(info, LANCER_SH)
    (DIST / "SHA256SUMS.txt").write_text(
        "".join(f"{sha256(p)}  {p.name}\n" for p in (pyz, bundle)), encoding="utf-8")
    (DIST / "RELEASE_NOTES.md").write_text(
        f"{notes}\n**Installation** : télécharger `{bundle.name}` (ou seulement `{pyz.name}`, à renommer "
        f"`checklist-livraison.pyz`) et suivre `INSTALLATION.md`. Python 3.8+ suffit.\n", encoding="utf-8")
    for p in (pyz, bundle):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024} Ko  sha256 {sha256(p)[:16]}…")


if __name__ == "__main__":
    main()
