"""Package the whole app (code, frontend, fonts) into one runnable file.

Usage: python tools/build_pyz.py [dist/checklist-livraison.pyz]
Run the result with: python checklist-livraison.pyz   (data/ is created next to it)
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAIN = '''import sys
from delivery_app.__main__ import main
sys.argv.append("--auto-open")  # opens the browser unless --no-browser or "navigateur = non"
main()
'''


def build(out):
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("__main__.py", MAIN)
        for path in sorted((ROOT / "delivery_app").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, path.relative_to(ROOT).as_posix())
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "checklist-livraison.pyz"
    print(f"Archive écrite : {build(target)} ({target.stat().st_size // 1024} Ko)")
