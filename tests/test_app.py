"""End-to-end API tests against a real server on a temporary database.

Run: python -m unittest discover tests
"""

import io
import json
import random
import sqlite3
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
import zlib
from pathlib import Path

from unittest import mock

from delivery_app import db as dbmod
from delivery_app import pdf_writer, report
from delivery_app.db import Database, SchemaTooNew
from delivery_app.server import make_server
from delivery_app.templating import build_variables, parse_table, render_command

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201e2213bc90000000049454e44ae426082")


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Database(Path(cls.tmp.name) / "test.db")
        cls.server = make_server(cls.db, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.server.RequestHandlerClass.log_message = lambda *args: None
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.db.conn.close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req) as res:
                payload = res.read()
                return res.status, json.loads(payload) if "json" in res.headers["Content-Type"] else payload
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_full_delivery_flow(self):
        status, tasks = self.call("GET", "/api/tasks")
        self.assertEqual(status, 200)
        self.assertGreater(len(tasks), 0)

        _, d = self.call("POST", "/api/deliveries", {"version": "3.1.0", "name": "Test",
                                                     "variables": {"prev_version": "3.0.2"}})
        self.assertEqual(len(d["tasks"]), len(tasks))
        self.assertEqual(d["progress"], 0)
        first, second = d["tasks"][0], d["tasks"][1]

        _, d = self.call("POST", f"/api/delivery-tasks/{first['id']}/action", {"action": "start"})
        self.assertEqual(d["tasks"][0]["status"], "running")
        self.assertIsNotNone(d["tasks"][0]["running_since"])
        _, d = self.call("POST", f"/api/delivery-tasks/{first['id']}/action", {"action": "done"})
        self.assertEqual(d["tasks"][0]["status"], "done")
        total = sum(t["weight"] for t in d["tasks"])
        self.assertEqual(d["progress"], round(100 * first["weight"] / total))

        # Skipped tasks leave the denominator.
        _, d = self.call("POST", f"/api/delivery-tasks/{second['id']}/action", {"action": "skip"})
        self.assertEqual(d["progress"], round(100 * first["weight"] / (total - second["weight"])))

        _, d = self.call("POST", f"/api/delivery-tasks/{first['id']}/comments", {"body": "RAS"})
        self.assertEqual(d["tasks"][0]["comments"][0]["body"], "RAS")

        status, d = self.call("POST", f"/api/delivery-tasks/{first['id']}/images", raw=PNG,
                              headers={"Content-Type": "image/png", "X-Filename": "capture%20tests.png"})
        self.assertEqual(status, 200)
        img = d["tasks"][0]["images"][0]
        self.assertEqual(img["filename"], "capture tests.png")
        status, blob = self.call("GET", img["url"])
        self.assertEqual(blob, PNG)

        for fmt, magic in (("pdf", b"%PDF"), ("docx", b"PK")):
            status, data = self.call("GET", f"/api/deliveries/{d['id']}/report.{fmt}")
            self.assertEqual(status, 200, data)
            self.assertTrue(data.startswith(magic))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn("word/media/image1.png", z.namelist())
            self.assertIn("https://wiki.example.com/releases/3.1.0", z.read("word/_rels/document.xml.rels").decode())

        with_tables = next(t for t in d["tasks"] if len(t["link_tables"]) > 1)
        for path, count in (("tables.docx", len(with_tables["link_tables"])), ("table.docx", 2), ("tables/1.docx", 1)):
            status, data = self.call("GET", f"/api/delivery-tasks/{with_tables['id']}/{path}")
            self.assertEqual(status, 200, path)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                document = z.read("word/document.xml").decode()
                self.assertEqual(document.count("<w:tbl>"), count, path)
                self.assertIn("<w:hyperlink", document)
        self.assertEqual(self.call("GET", f"/api/delivery-tasks/{with_tables['id']}/tables/9.docx")[0], 400)
        self.assertEqual(self.call("GET", f"/api/delivery-tasks/{first['id']}/tables.docx")[0], 400)

        _, d = self.call("PUT", f"/api/deliveries/{d['id']}", {"status": "done"})
        self.assertEqual(d["status"], "done")
        self.assertIsNotNone(d["completed_at"])
        _, listing = self.call("GET", "/api/deliveries")
        self.assertIn(d["id"], [x["id"] for x in listing])

    def test_template_changes_do_not_rewrite_history(self):
        _, d = self.call("POST", "/api/deliveries", {"version": "1.0.0"})
        tpl_id = d["tasks"][0]["template_task_id"]
        self.call("PUT", f"/api/tasks/{tpl_id}", {"title": "Titre modifié"})
        _, again = self.call("GET", f"/api/deliveries/{d['id']}")
        self.assertNotEqual(again["tasks"][0]["title"], "Titre modifié")

    def test_add_task_to_delivery_and_template(self):
        _, before = self.call("GET", "/api/tasks")
        _, d = self.call("POST", "/api/deliveries", {"version": "1.2.0"})
        _, d = self.call("POST", f"/api/deliveries/{d['id']}/tasks",
                         {"title": "Nouvelle", "weight": 2, "estimated_minutes": 5, "add_to_template": True,
                          "commands": [{"label": " Linux ", "text": "echo {{version}}"}, {"label": "vide", "text": "  "},
                                       {"text": "dir"}],
                          "link_tables": [{"title": "A", "spec": "x | y"}, {"title": "B", "spec": ""}]})
        task = d["tasks"][-1]
        self.assertEqual(task["title"], "Nouvelle")
        self.assertEqual(task["commands"], [{"label": "Linux", "text": "echo {{version}}"}, {"label": "", "text": "dir"}])
        self.assertEqual(task["link_tables"], [{"title": "A", "spec": "x | y"}])
        self.assertNotIn("command", task)
        _, d = self.call("PUT", f"/api/delivery-tasks/{task['id']}", {"title": "Renommée"})
        self.assertEqual(d["tasks"][-1]["commands"], task["commands"])  # untouched lists are kept
        _, after = self.call("GET", "/api/tasks")
        self.assertEqual(len(after), len(before) + 1)

    def test_template_screenshots_are_copied_into_deliveries(self):
        _, tasks = self.call("GET", "/api/tasks")
        tpl = tasks[1]
        status, tasks = self.call("POST", f"/api/tasks/{tpl['id']}/images", raw=PNG,
                                  headers={"Content-Type": "image/png", "X-Filename": "attendu.png"})
        self.assertEqual(status, 200)
        ref = next(t for t in tasks if t["id"] == tpl["id"])["images"][0]
        self.assertEqual(self.call("GET", ref["url"])[1], PNG)

        _, d = self.call("POST", "/api/deliveries", {"version": "4.0.0"})
        task = next(t for t in d["tasks"] if t["template_task_id"] == tpl["id"])
        self.assertEqual([(i["filename"], i["reference"]) for i in task["images"]], [("attendu.png", True)])

        # Removing it from the template leaves the delivery's copy alone (history is never rewritten).
        _, tasks = self.call("DELETE", ref["url"])
        self.assertEqual(next(t for t in tasks if t["id"] == tpl["id"])["images"], [])
        _, d = self.call("GET", f"/api/deliveries/{d['id']}")
        task = next(t for t in d["tasks"] if t["template_task_id"] == tpl["id"])
        self.assertEqual(len(task["images"]), 1)

        # A screenshot taken during a delivery can become the template's reference.
        _, d = self.call("POST", f"/api/delivery-tasks/{task['id']}/images", raw=PNG,
                         headers={"Content-Type": "image/png", "X-Filename": "nouvelle.png"})
        own = next(i for i in next(t for t in d["tasks"] if t["id"] == task["id"])["images"] if not i["reference"])
        status, _ = self.call("POST", f"/api/images/{own['id']}/to-template")
        self.assertEqual(status, 200)
        _, tasks = self.call("GET", "/api/tasks")
        self.assertEqual([i["filename"] for i in next(t for t in tasks if t["id"] == tpl["id"])["images"]],
                         ["nouvelle.png"])
        for fmt in ("pdf", "docx"):
            self.assertEqual(self.call("GET", f"/api/deliveries/{d['id']}/report.{fmt}")[0], 200)

    def test_static_files_and_traversal(self):
        req = urllib.request.urlopen(self.base + "/fonts/fonts.css")
        self.assertIn(b"@font-face", req.read())
        status, _ = self.call("GET", "/../db.py")
        self.assertEqual(status, 404)
        status, _ = self.call("GET", "/%2e%2e/db.py")
        self.assertEqual(status, 404)

    def test_validation_errors(self):
        status, body = self.call("POST", "/api/deliveries", {"version": "  "})
        self.assertEqual(status, 400)
        self.assertIn("version", body["error"])
        status, _ = self.call("POST", "/api/delivery-tasks/1/images", raw=b"x",
                              headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _ = self.call("GET", "/api/deliveries/99999")
        self.assertEqual(status, 404)


def make_png(width, height, channels, seed=1):
    """RGBA/RGB PNG using every filter type, plus the raw pixels it encodes."""
    rnd = random.Random(seed)
    stride = width * channels
    pixels = bytes(rnd.randrange(256) for _ in range(stride * height))
    raw, prev = bytearray(), bytes(stride)
    for y in range(height):
        row = pixels[y * stride:(y + 1) * stride]
        ftype = y % 5
        out = bytearray()
        for i in range(stride):
            a = row[i - channels] if i >= channels else 0
            b, c = prev[i], (prev[i - channels] if i >= channels else 0)
            pred = [0, a, b, (a + b) >> 1, None][ftype]
            if ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
            out.append((row[i] - pred) & 255)
        raw += bytes([ftype]) + out
        prev = row

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ctype = {3: 2, 4: 6}[channels]
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, ctype, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
    return png, pixels


class WritersTest(unittest.TestCase):
    def test_png_unfilter_matches_source(self):
        png, pixels = make_png(23, 17, 4)
        idat = png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8]
        self.assertEqual(pdf_writer._unfilter(zlib.decompress(idat), 23, 17, 4), pixels)

    def test_pdf_with_images_tables_and_links(self):
        doc = pdf_writer.Pdf("Essai", footer="Essai")
        doc.text("Élément accentué — « ok » " * 30)
        doc.table([[[("A", pdf_writer.BOLD, pdf_writer.WHITE, None)], [("B", pdf_writer.BOLD, pdf_writer.WHITE, None)]],
                   [[("x", pdf_writer.REGULAR, pdf_writer.INK, None)],
                    [("lien", pdf_writer.REGULAR, pdf_writer.LINK, "https://example.com/a?b=(c)")]]] * 40)
        doc.image(make_png(40, 30, 4)[0])
        doc.image(make_png(40, 30, 3)[0])
        data = doc.to_bytes()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertIn(b"/URI (https://example.com/a?b=\\(c\\))", data)
        self.assertIn(b"/SMask", data)
        self.assertGreater(data.count(b"/Type /Page "), 1)


class RenderTest(unittest.TestCase):
    def test_parse_table(self):
        table = parse_table("| Élément | Lien |\n|---|---|\nNotes | [Wiki {{version}}](https://w/{{version}})\n"
                            "Tag | voir https://git/v{{version}} ici\nSeul", {"version": "1.2"})
        self.assertEqual(table["headers"], [[("Élément", None)], [("Lien", None)]])
        self.assertEqual(table["rows"][0][1], [("Wiki 1.2", "https://w/1.2")])
        self.assertEqual(table["rows"][1][1], [("voir ", None), ("https://git/v1.2", "https://git/v1.2"), (" ici", None)])
        self.assertEqual(table["rows"][2], [[("Seul", None)], []])
        self.assertIsNone(parse_table("  \n", {}))

    def test_variables(self):
        variables = build_variables({"version": "2.4.1", "name": "x", "created_at": "2026-01-02T10:00:00Z",
                                     "variables": {"env": "prod"}})
        self.assertEqual(render_command("v{{version}} {{ major }}.{{minor}} {{env}} {{unknown}}", variables),
                         "v2.4.1 2.4 prod {{unknown}}")
        self.assertEqual(variables["date"], "2026-01-02")


FIXTURES = Path(__file__).parent / "fixtures"
TABLES = ("settings", "template_tasks", "deliveries", "delivery_tasks", "comments", "images")


def load_fixture(version, directory):
    path = Path(directory) / f"v{version}.db"
    conn = sqlite3.connect(str(path))
    conn.executescript((FIXTURES / f"schema_v{version}.sql").read_text(encoding="utf-8"))
    conn.close()
    return path


def schema_of(conn):
    """Columns and indexes per table, to compare a migrated database with a fresh one."""
    out = {}
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        cols = sorted((r[1], r[2].upper(), r[3], r[4], r[5]) for r in conn.execute(f"PRAGMA table_info({table})"))
        out[table] = cols
    out["_indexes"] = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"))
    return out


class CompatibilityTest(unittest.TestCase):
    """Every frozen schema version (tests/fixtures) must open, upgrade and work with the current app."""

    def versions(self):
        return sorted(int(p.stem.split("_v")[1]) for p in FIXTURES.glob("schema_v*.sql"))

    def test_every_version_has_a_fixture(self):
        self.assertEqual(self.versions(), list(range(1, dbmod.SCHEMA_VERSION + 1)),
                         "Lancez tools/snapshot_schema.py pour figer chaque version du schéma.")

    def test_old_databases_upgrade_without_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Database(Path(tmp) / "fresh.db")
            expected_schema = schema_of(fresh.conn)
            fresh.conn.close()
            for version in self.versions():
                with self.subTest(version=version):
                    path = load_fixture(version, tmp)
                    raw = sqlite3.connect(str(path))
                    counts = {t: raw.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
                    comments = raw.execute("SELECT body FROM comments ORDER BY id").fetchall()
                    images = raw.execute("SELECT data FROM images ORDER BY id").fetchall()
                    raw.close()

                    db = Database(path)
                    self.assertEqual(schema_of(db.conn), expected_schema)
                    for table, count in counts.items():
                        self.assertEqual(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], count, table)
                    self.assertEqual([tuple(r) for r in db.conn.execute("SELECT body FROM comments ORDER BY id")], comments)
                    self.assertEqual([tuple(r) for r in db.conn.execute("SELECT data FROM images ORDER BY id")], images)
                    if version < dbmod.SCHEMA_VERSION:
                        self.assertTrue(db.backup_path and db.backup_path.exists())

                    # The upgraded database works end to end.
                    for summary in db.list_deliveries():
                        d = db.get_delivery(summary["id"])
                        self.assertTrue(report.build_pdf(d, db).startswith(b"%PDF"))
                        self.assertTrue(report.build_docx(d, db).startswith(b"PK"))
                    d = db.create_delivery({"version": "9.9.9"})
                    d = db.task_action(d["tasks"][0]["id"], "done")
                    self.assertGreater(d["progress"], 0)
                    db.conn.close()

    def test_v2_single_command_and_table_become_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = load_fixture(2, tmp)
            raw = sqlite3.connect(str(path))
            legacy = {r[0]: (r[1], r[2]) for r in raw.execute("SELECT id, command, table_spec FROM delivery_tasks")}
            raw.close()
            db = Database(path)
            for task_id, (command, spec) in legacy.items():
                task = db.get_delivery_task(task_id)
                self.assertEqual(task["commands"], [{"label": "", "text": command}] if command.strip() else [])
                self.assertEqual(task["link_tables"], [{"title": "", "spec": spec}] if spec.strip() else [])
            self.assertTrue(any(spec.strip() for _, spec in legacy.values()))
            db.conn.close()

    def test_newer_database_is_refused_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = load_fixture(dbmod.SCHEMA_VERSION, tmp)
            raw = sqlite3.connect(str(path))
            raw.execute("UPDATE settings SET value=? WHERE key='schema_version'", (str(dbmod.SCHEMA_VERSION + 1),))
            raw.commit()
            raw.close()
            with self.assertRaises(SchemaTooNew):
                Database(path)
            raw = sqlite3.connect(str(path))
            self.assertEqual(raw.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0],
                             str(dbmod.SCHEMA_VERSION + 1))
            raw.close()

    def test_failed_migration_rolls_back(self):
        def broken(conn):
            conn.execute("ALTER TABLE deliveries ADD COLUMN half_done TEXT")
            raise RuntimeError("étape en échec")

        nxt = dbmod.SCHEMA_VERSION + 1
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(dbmod.MIGRATIONS, {nxt: broken}), mock.patch.object(dbmod, "SCHEMA_VERSION", nxt):
            path = load_fixture(nxt - 1, tmp)
            with self.assertRaises(RuntimeError):
                Database(path)
            raw = sqlite3.connect(str(path))
            cols = {r[1] for r in raw.execute("PRAGMA table_info(deliveries)")}
            self.assertNotIn("half_done", cols)
            self.assertEqual(raw.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0],
                             str(nxt - 1))
            raw.close()


if __name__ == "__main__":
    unittest.main()
