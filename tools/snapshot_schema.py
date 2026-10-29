"""Freeze a sample database of the current schema version into tests/fixtures/schema_vN.sql.

Run it once per released schema version, BEFORE changing the schema, and commit the file:
the tests then upgrade every frozen version to the current one and check nothing is lost.

Usage:
  python tools/snapshot_schema.py                 # snapshot of this checkout
  python tools/snapshot_schema.py --app OLD_DIR   # snapshot made by an older copy of the app
"""

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

# 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201e2213bc90000000049454e44ae426082")


def populate(db):
    """Sample data touching every table (calls added later are guarded by hasattr)."""
    db.save_settings({"default_variables": {"prev_version": "", "env": "recette"}})
    db.create_template_task({"title": "Tâche ajoutée au modèle", "command": "echo {{version}}",
                             "weight": 2, "estimated_minutes": 5})
    if hasattr(db, "add_template_image"):  # schema v4+
        db.add_template_image(db.list_template_tasks()[0]["id"], "reference.png", "image/png", PNG)
    if hasattr(db, "add_media"):  # schema v5+: content blocks
        image = db.add_media("reference.png", "image/png", PNG)
        tpl = db.list_template_tasks()[0]
        db.update_template_task(tpl["id"], {"blocks": tpl["blocks"] + [
            {"type": "link", "label": "Pipeline", "url": "https://ci.example.com/{{version}}"},
            {"type": "program", "name": "Outil", "path": "/opt/outil", "args": "--v {{version}}"},
            {"type": "note", "text": "Consigne"},
            {"type": "media", "title": "Écran attendu", "files": [image]}]})
    if "enabled" in db.list_template_tasks()[0]:  # schema v7+: a disabled template task
        disabled = db.create_template_task({"title": "Tâche désactivée", "estimated_minutes": 2})
        db.update_template_task(disabled["id"], {"enabled": False})
    if "alarm" in db.list_template_tasks()[0]:  # schema v8+: a waiting task ("cloche")
        db.create_template_task({"title": "Attendre la fin du déploiement", "estimated_minutes": 15, "alarm": True})
    closed = db.create_delivery({"version": "1.0.0", "name": "Ancienne livraison",
                                 "variables": {"prev_version": "0.9.0", "env": "prod"}})
    for t in closed["tasks"]:
        db.task_action(t["id"], "start")
        db.task_action(t["id"], "done")
    first = closed["tasks"][0]["id"]
    db.add_comment(first, "Commentaire historique — accents éàç")
    db.add_image(first, "capture.png", "image/png", PNG)
    db.update_delivery(closed["id"], {"status": "done"})

    current = db.create_delivery({"version": "1.1.0", "variables": {"prev_version": "1.0.0"}})
    db.task_action(current["tasks"][0]["id"], "start")
    db.task_action(current["tasks"][1]["id"], "skip")
    db.add_delivery_task(current["id"], {"title": "Tâche ad hoc", "weight": 1, "estimated_minutes": 3})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=ROOT, help="dossier racine de la version de l'app à figer")
    args = parser.parse_args()
    sys.path.insert(0, str(args.app.resolve()))
    from delivery_app import db as dbmod

    with tempfile.TemporaryDirectory() as tmp:
        db = dbmod.Database(Path(tmp) / "snap.db")
        populate(db)
        version = int(db.conn.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0])
        db.conn.close()
        conn = sqlite3.connect(str(Path(tmp) / "snap.db"))
        dump = "\n".join(conn.iterdump()) + "\n"
        conn.close()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    out = FIXTURES / f"schema_v{version}.sql"
    out.write_text(dump, encoding="utf-8")
    print(f"Base d'exemple v{version} figée dans {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
