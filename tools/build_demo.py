"""Build a single-file demo (in-memory mock API) of the frontend.

Usage: python tools/build_demo.py [output.html]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "delivery_app" / "static"


def build():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    mock = (ROOT / "tools" / "mock-api.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    return f"""<title>Checklist Livraison</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
{css}
</style>
<div id="app" class="app"></div>
<script>
{mock}
</script>
<script>
{app}
</script>
"""


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo.html"
    out.write_text(build(), encoding="utf-8")
    print(f"Démo écrite dans {out}")
