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

from delivery_app import pdf_writer
from delivery_app.db import Database
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

        with_table = next(t for t in d["tasks"] if t["table_spec"])
        status, data = self.call("GET", f"/api/delivery-tasks/{with_table['id']}/table.docx")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            document = z.read("word/document.xml").decode()
            self.assertIn("<w:tbl>", document)
            self.assertIn("<w:hyperlink", document)
        status, body = self.call("GET", f"/api/delivery-tasks/{first['id']}/table.docx")
        self.assertEqual(status, 400)

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
                         {"title": "Nouvelle", "command": "echo {{version}}", "weight": 2,
                          "estimated_minutes": 5, "add_to_template": True})
        self.assertEqual(d["tasks"][-1]["title"], "Nouvelle")
        _, after = self.call("GET", "/api/tasks")
        self.assertEqual(len(after), len(before) + 1)

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


class MigrationTest(unittest.TestCase):
    def test_v1_database_gets_table_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO settings VALUES ('schema_version', '1'), ('default_variables', '{}');
                CREATE TABLE template_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, position INTEGER NOT NULL DEFAULT 0,
                    title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', command TEXT NOT NULL DEFAULT '',
                    weight INTEGER NOT NULL DEFAULT 1, estimated_minutes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                INSERT INTO template_tasks (title, created_at, updated_at) VALUES ('Ancienne', 'x', 'x');
                CREATE TABLE delivery_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_id INTEGER NOT NULL,
                    template_task_id INTEGER, position INTEGER NOT NULL DEFAULT 0, title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '', command TEXT NOT NULL DEFAULT '',
                    weight INTEGER NOT NULL DEFAULT 1, estimated_minutes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'todo', elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    running_since TEXT, started_at TEXT, completed_at TEXT);
            """)
            conn.commit()
            conn.close()
            db = Database(path)
            tasks = db.list_template_tasks()
            self.assertEqual(tasks[0]["table_spec"], "")
            d = db.create_delivery({"version": "1.0"})
            self.assertEqual(d["tasks"][0]["title"], "Ancienne")
            self.assertEqual(db.conn.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0], "2")
            db.conn.close()


if __name__ == "__main__":
    unittest.main()
