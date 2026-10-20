"""Build a single-file demo (in-memory mock API) of the frontend.

Usage: python tools/build_demo.py [output.html]
"""

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "delivery_app" / "static"


def inline_fonts():
    """fonts.css with every woff2 inlined as a data: URI (the demo is a single file)."""
    fonts = STATIC / "fonts"

    def data_uri(m):
        b64 = base64.b64encode((fonts / m.group(1)).read_bytes()).decode()
        return f"url(data:font/woff2;base64,{b64})"
    return re.sub(r"url\(([\w.-]+\.woff2)\)", data_uri, (fonts / "fonts.css").read_text(encoding="utf-8"))


def build():
    css = inline_fonts() + "\n" + (STATIC / "style.css").read_text(encoding="utf-8")
    mock = (ROOT / "tools" / "mock-api.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    blocks = (STATIC / "blocks.js").read_text(encoding="utf-8")
    return f"""<title>Checklist Livraison</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
{css}
</style>
<div id="app" class="app"></div>
<script>
{mock}
</script>
<script>
{blocks}
</script>
<script>
{app}
</script>
"""


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo.html"
    out.write_text(build(), encoding="utf-8")
    print(f"Démo écrite dans {out}")
