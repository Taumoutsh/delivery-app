"""End-to-end API tests against a real server on a temporary database.

Run: python -m unittest discover tests
"""

import io
import json
import os
import random
import re
import sqlite3
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from unittest import mock

from delivery_app import db as dbmod
from delivery_app import pdf_writer, report
from delivery_app.db import Database, SchemaTooNew
from delivery_app.server import make_server
from delivery_app.templating import build_variables, parse_inline, parse_rich, parse_table, render_command

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

    def call(self, method, path, body=None, raw=None, headers=None, app=True):
        """API call as the UI makes it (app=False: without the X-Checklist header)."""
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={**({"X-Checklist": "1"} if app else {}), **(headers or {})})
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
        # Progress is weighted by estimated time.
        total = sum(max(1, t["estimated_minutes"]) for t in d["tasks"])
        self.assertEqual(d["progress"], round(100 * first["estimated_minutes"] / total))
        self.assertNotIn("weight", first)

        # Skipped tasks leave the denominator.
        _, d = self.call("POST", f"/api/delivery-tasks/{second['id']}/action", {"action": "skip"})
        self.assertEqual(d["progress"], round(100 * first["estimated_minutes"] / (total - second["estimated_minutes"])))

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

        with_tables = next(t for t in d["tasks"] if sum(b["type"] == "table" for b in t["blocks"]) > 1)
        second_table = [b for b in with_tables["blocks"] if b["type"] == "table"][1]
        for path, count in (("tables.docx", 2), ("table.docx", 2), (f"tables/{second_table['id']}.docx", 1)):
            status, data = self.call("GET", f"/api/delivery-tasks/{with_tables['id']}/{path}")
            self.assertEqual(status, 200, path)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                document = z.read("word/document.xml").decode()
                self.assertEqual(document.count("<w:tbl>"), count, path)
                self.assertIn("<w:hyperlink", document)
        self.assertEqual(self.call("GET", f"/api/delivery-tasks/{with_tables['id']}/tables/inconnu.docx")[0], 400)
        self.assertEqual(self.call("GET", f"/api/delivery-tasks/{first['id']}/tables.docx")[0], 400)

        _, d = self.call("PUT", f"/api/deliveries/{d['id']}", {"status": "done"})
        self.assertEqual(d["status"], "done")
        self.assertIsNotNone(d["completed_at"])
        _, listing = self.call("GET", "/api/deliveries")
        self.assertIn(d["id"], [x["id"] for x in listing])

    def test_formatted_note_in_reports(self):
        _, d = self.call("POST", "/api/deliveries", {"version": "6.2.0"})
        _, d = self.call("POST", f"/api/deliveries/{d['id']}/tasks", {"title": "Notes", "blocks": [{"type": "note", "text":
            "Avant **{{version}}** : *prévenir* __le support__ ~~hier~~\n\n- Point un\n\t- Sous-point\n- Point **deux**\n\n1. Étape\n2. Suite"}]})
        _, docx = self.call("GET", f"/api/deliveries/{d['id']}/report.docx")
        document = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode()
        for expected in ("<w:b/>", "<w:i/>", '<w:u w:val="single"/>', "<w:strike/>", ">6.2.0<", ">•<", ">2.<", "<w:tab/>",
                         ">◦<", 'w:left="1134"'):
            self.assertIn(expected, document)
        self.assertNotIn("**", document)
        _, report = self.call("GET", f"/api/deliveries/{d['id']}/report.pdf")
        content = pdf_content(report)
        self.assertIn(b"/BaseFont /Helvetica-BoldOblique", report)
        self.assertIn(b"/F2 9.50 Tf", content)  # bold
        self.assertIn(b"/F3 9.50 Tf", content)  # italic
        self.assertIn(b"(\x95) Tj", content)  # bullet (cp1252)
        self.assertNotIn(b"**", content)

    def test_timers_are_chained(self):
        status = lambda d: [t["status"] for t in d["tasks"]]  # noqa: E731
        _, d = self.call("POST", "/api/deliveries", {"version": "8.0.0"})
        self.assertEqual(status(d)[:3], ["running", "todo", "todo"])  # first task starts with the delivery
        self.assertIsNotNone(d["tasks"][0]["started_at"])
        t = d["tasks"]
        _, d = self.call("POST", f"/api/delivery-tasks/{t[0]['id']}/action", {"action": "done"})
        self.assertEqual(status(d)[:3], ["done", "running", "todo"])
        # Skipping a task not started yet hands over to the one after it, not to an earlier one.
        self.call("POST", f"/api/delivery-tasks/{t[1]['id']}/action", {"action": "pause"})
        _, d = self.call("POST", f"/api/delivery-tasks/{t[2]['id']}/action", {"action": "skip"})
        self.assertEqual(status(d)[:4], ["done", "paused", "skipped", "running"])
        # No chaining while another timer runs.
        _, d = self.call("POST", f"/api/delivery-tasks/{t[1]['id']}/action", {"action": "done"})
        self.assertEqual(status(d)[:4], ["done", "done", "skipped", "running"])
        self.assertEqual(status(d).count("running"), 1)
        # After the last task, the earlier tasks still to do are taken back from the top.
        last = d["tasks"][-1]
        for x in d["tasks"][3:-1]:
            self.call("POST", f"/api/delivery-tasks/{x['id']}/action", {"action": "pause"})
        _, d = self.call("POST", f"/api/delivery-tasks/{last['id']}/action", {"action": "skip"})
        self.assertEqual(status(d)[3], "running")

        _, settings = self.call("PUT", "/api/settings", {"auto_timer": False})
        self.assertFalse(settings["auto_timer"])
        try:
            _, d = self.call("POST", "/api/deliveries", {"version": "8.0.1"})
            self.assertNotIn("running", status(d))
            _, d = self.call("POST", f"/api/delivery-tasks/{d['tasks'][0]['id']}/action", {"action": "done"})
            self.assertNotIn("running", status(d))
        finally:
            self.call("PUT", "/api/settings", {"auto_timer": True})

    def test_storage_api(self):
        status, report = self.call("GET", "/api/storage")
        self.assertEqual(status, 200)
        self.assertEqual(set(report), {"file_bytes", "journal_bytes", "content", "reclaimable", "backups"})
        self.assertEqual(self.call("POST", "/api/storage/cleanup", {}, app=False)[0], 403)
        status, report = self.call("POST", "/api/storage/cleanup", {})
        self.assertEqual(status, 200)
        self.assertEqual(report["reclaimable"]["free_bytes"], 0)

    def test_template_changes_do_not_rewrite_history(self):
        _, d = self.call("POST", "/api/deliveries", {"version": "1.0.0"})
        tpl_id = d["tasks"][0]["template_task_id"]
        self.call("PUT", f"/api/tasks/{tpl_id}", {"title": "Titre modifié"})
        _, again = self.call("GET", f"/api/deliveries/{d['id']}")
        self.assertNotEqual(again["tasks"][0]["title"], "Titre modifié")

    def test_add_task_to_delivery_and_template(self):
        _, before = self.call("GET", "/api/tasks")
        _, d = self.call("POST", "/api/deliveries", {"version": "1.2.0"})
        _, d = self.call("POST", f"/api/deliveries/{d['id']}/tasks", {
            "title": "Nouvelle", "estimated_minutes": 5, "add_to_template": True, "blocks": [
                {"id": "c1", "type": "command", "label": " Linux ", "text": "echo {{version}}"},
                {"type": "command", "label": "vide", "text": "  "},
                {"type": "link", "label": "CI", "url": " https://ci/{{version}} "},
                {"type": "program", "name": "Outil", "path": "/usr/bin/true", "args": "--v {{version}}"},
                {"type": "note", "text": "Attention"},
                {"type": "table", "title": "A", "spec": "x | y"}, {"type": "table", "title": "B", "spec": ""}]})
        task = d["tasks"][-1]
        self.assertEqual(task["title"], "Nouvelle")
        self.assertEqual([b["type"] for b in task["blocks"]], ["command", "link", "program", "note", "table"])
        self.assertEqual(task["blocks"][0], {"id": "c1", "type": "command", "label": "Linux", "text": "echo {{version}}"})
        self.assertEqual(task["blocks"][1]["url"], "https://ci/{{version}}")
        self.assertTrue(all(b["id"] for b in task["blocks"]))
        _, d = self.call("PUT", f"/api/delivery-tasks/{task['id']}", {"title": "Renommée"})
        self.assertEqual(d["tasks"][-1]["blocks"], task["blocks"])  # untouched blocks are kept
        _, after = self.call("GET", "/api/tasks")
        self.assertEqual(len(after), len(before) + 1)
        status, body = self.call("PUT", f"/api/delivery-tasks/{task['id']}", {"blocks": [{"type": "inconnu"}]})
        self.assertEqual(status, 400)

    def upload(self, path, data, mime, name):
        return self.call("POST", path, raw=data, headers={"Content-Type": mime, "X-Filename": name})

    def test_media_blocks_are_shared_with_deliveries_without_rewriting_history(self):
        status, image = self.upload("/api/media", PNG, "image/png", "attendu.png")
        self.assertEqual(status, 200)
        video = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 4
        _, clip = self.upload("/api/media", video, "video/mp4", "demo.mp4")
        _, tasks = self.call("GET", "/api/tasks")
        tpl = tasks[1]
        _, tpl = self.call("PUT", f"/api/tasks/{tpl['id']}", {"blocks": tpl["blocks"] + [
            {"type": "media", "title": "Écran attendu", "files": [image, {"id": clip["id"]}]}]})
        media = tpl["blocks"][-1]
        self.assertEqual([f["filename"] for f in media["files"]], ["attendu.png", "demo.mp4"])
        self.assertEqual(self.call("GET", media["files"][0]["url"])[1], PNG)

        # Videos can be read by ranges (seeking in the player).
        req = urllib.request.Request(self.base + clip["url"], headers={"Range": "bytes=10-19"})
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 206)
            self.assertEqual(res.read(), video[10:20])
            self.assertEqual(res.headers["Content-Range"], f"bytes 10-19/{len(video)}")

        _, d = self.call("POST", "/api/deliveries", {"version": "4.0.0"})
        task = next(t for t in d["tasks"] if t["template_task_id"] == tpl["id"])
        self.assertEqual(task["blocks"][-1]["files"], media["files"])

        # Removing the files from the template leaves the delivery's element alone.
        self.call("PUT", f"/api/tasks/{tpl['id']}", {"blocks": tpl["blocks"][:-1]})
        self.assertEqual(self.db.collect_media(), 0)  # still used by the delivery (and recent anyway)
        _, d = self.call("GET", f"/api/deliveries/{d['id']}")
        task = next(t for t in d["tasks"] if t["template_task_id"] == tpl["id"])
        self.assertEqual(len(task["blocks"][-1]["files"]), 2)

        # A screenshot taken during a delivery can join the template's media element.
        _, d = self.upload(f"/api/delivery-tasks/{task['id']}/images", PNG, "image/png", "nouvelle.png")
        own = next(t for t in d["tasks"] if t["id"] == task["id"])["images"][0]
        self.assertEqual(self.call("POST", f"/api/images/{own['id']}/to-template")[0], 200)
        _, tasks = self.call("GET", "/api/tasks")
        tpl_media = next(t for t in tasks if t["id"] == tpl["id"])["blocks"][-1]
        self.assertEqual((tpl_media["title"], [f["filename"] for f in tpl_media["files"]]),
                         ("Captures de référence", ["nouvelle.png"]))
        for fmt in ("pdf", "docx"):
            status, data = self.call("GET", f"/api/deliveries/{d['id']}/report.{fmt}")
            self.assertEqual(status, 200)
        self.assertIn("demo.mp4", data.decode("latin-1") if False else zipfile.ZipFile(io.BytesIO(data))
                      .read("word/document.xml").decode())
        self.assertEqual(self.upload("/api/media", b"x", "application/zip", "a.zip")[0], 415)

    def test_any_video_format_is_accepted(self):
        for mime, name in (("video/x-msvideo", "demo.avi"), ("video/x-matroska", "demo.mkv"),
                           ("video/x-ms-wmv", "demo.wmv")):
            status, clip = self.upload("/api/media", b"video", mime, name)
            self.assertEqual(status, 200, name)
            self.assertEqual(clip["mime"], mime)
        # Browsers send no type (or a generic one) for some files: deduce it from the extension.
        status, clip = self.upload("/api/media", b"video", "application/octet-stream", "demo.mkv")
        self.assertEqual((status, clip["mime"]), (200, "video/x-matroska"))
        status, body = self.upload("/api/media", b"x", "application/octet-stream", "notes.bin")
        self.assertEqual(status, 415)
        self.assertIn("notes.bin", body["error"])
        # Delivery captures stay images only.
        _, d = self.call("POST", "/api/deliveries", {"version": "4.1.0"})
        status, _ = self.upload(f"/api/delivery-tasks/{d['tasks'][0]['id']}/images", b"v", "video/mp4", "a.mp4")
        self.assertEqual(status, 415)

    def test_launch_program_block(self):
        marker = Path(self.tmp.name) / "lance.txt"
        script = Path(self.tmp.name) / "outil.sh"
        script.write_text(f'#!/bin/sh\necho "$@" > "{marker}"\n')
        script.chmod(0o755)
        _, d = self.call("POST", "/api/deliveries", {"version": "7.1.0", "variables": {"opts": "--version {{version}}"}})
        _, d = self.call("POST", f"/api/deliveries/{d['id']}/tasks", {"title": "Lancer", "blocks": [
            {"id": "p1", "type": "program", "name": "Outil", "path": str(script), "args": "{{opts}}"},
            {"id": "p2", "type": "program", "name": "Absent", "path": "/nulle/part/outil"}]})
        task = d["tasks"][-1]
        status, body = self.call("POST", f"/api/delivery-tasks/{task['id']}/blocks/p1/launch")
        self.assertEqual(status, 200, body)
        for _ in range(50):
            if marker.exists() and marker.read_text().strip():
                break
            time.sleep(0.05)
        self.assertEqual(marker.read_text().strip(), "--version 7.1.0")
        status, body = self.call("POST", f"/api/delivery-tasks/{task['id']}/blocks/p2/launch")
        self.assertEqual(status, 422)
        self.assertIn("introuvable", body["error"])
        self.assertEqual(self.call("POST", f"/api/delivery-tasks/{task['id']}/blocks/zz/launch")[0], 404)
        # Refused without the app header (a page from another site cannot add it).
        self.assertEqual(self.call("POST", f"/api/delivery-tasks/{task['id']}/blocks/p1/launch", app=False)[0], 403)
        self.server.RequestHandlerClass.allow_launch = False
        try:
            self.assertEqual(self.call("POST", f"/api/delivery-tasks/{task['id']}/blocks/p1/launch")[0], 403)
        finally:
            self.server.RequestHandlerClass.allow_launch = True

    def test_closed_delivery_is_read_only_until_reopened(self):
        _, d = self.call("POST", "/api/deliveries", {"version": "9.1.0"})
        task = d["tasks"][0]
        self.call("POST", f"/api/delivery-tasks/{task['id']}/action", {"action": "start"})
        self.call("POST", f"/api/delivery-tasks/{task['id']}/comments", {"body": "avant clôture"})
        _, d = self.upload(f"/api/delivery-tasks/{task['id']}/images", PNG, "image/png", "c.png")
        comment, image = d["tasks"][0]["comments"][0], d["tasks"][0]["images"][0]

        _, d = self.call("PUT", f"/api/deliveries/{d['id']}", {"status": "done"})
        self.assertEqual(d["tasks"][0]["status"], "paused")  # closing stops running timers
        self.assertIsNone(d["tasks"][0]["running_since"])

        tid, did = task["id"], d["id"]
        refused = [
            ("PUT", f"/api/deliveries/{did}", {"name": "x"}),
            ("PUT", f"/api/deliveries/{did}", {"variables": {"env": "x"}}),
            ("DELETE", f"/api/deliveries/{did}", None),
            ("POST", f"/api/deliveries/{did}/tasks", {"title": "x"}),
            ("POST", f"/api/deliveries/{did}/reorder", {"ids": [tid]}),
            ("PUT", f"/api/delivery-tasks/{tid}", {"title": "x"}),
            ("DELETE", f"/api/delivery-tasks/{tid}", None),
            ("POST", f"/api/delivery-tasks/{tid}/action", {"action": "done"}),
            ("POST", f"/api/delivery-tasks/{tid}/comments", {"body": "x"}),
            ("DELETE", f"/api/comments/{comment['id']}", None),
            ("DELETE", f"/api/images/{image['id']}", None),
        ]
        for method, path, body in refused:
            status, err = self.call(method, path, body)
            self.assertEqual(status, 409, f"{method} {path}")
            self.assertIn("rouvrez", err["error"])
        self.assertEqual(self.upload(f"/api/delivery-tasks/{tid}/images", PNG, "image/png", "d.png")[0], 409)
        # Reading, exporting and copying to the template stay possible.
        self.assertEqual(self.call("GET", f"/api/deliveries/{did}/report.pdf")[0], 200)
        self.assertEqual(self.call("POST", f"/api/images/{image['id']}/to-template")[0], 200)

        _, d = self.call("PUT", f"/api/deliveries/{did}", {"status": "in_progress", "name": "ignoré"})
        self.assertEqual((d["status"], d["completed_at"], d["name"]), ("in_progress", None, ""))
        status, d = self.call("POST", f"/api/delivery-tasks/{tid}/action", {"action": "done"})
        self.assertEqual((status, d["tasks"][0]["status"]), (200, "done"))

    def test_variables_in_task_title(self):
        _, d = self.call("POST", "/api/deliveries", {"version": "3.4.0", "variables": {"env": "recette"}})
        _, d = self.call("POST", f"/api/deliveries/{d['id']}/tasks", {
            "title": "Déployer {{version}} en {{env}}",
            "blocks": [{"type": "table", "title": "", "spec": "A | B\nx | y"}]})
        task = d["tasks"][-1]
        self.assertEqual(task["title"], "Déployer {{version}} en {{env}}")  # stored as written
        _, pdf = self.call("GET", f"/api/deliveries/{d['id']}/report.pdf")
        content = pdf_content(pdf)  # the PDF draws words one by one
        self.assertIn("(Déployer) Tj ET".encode("cp1252"), content)
        self.assertIn(b"(recette) Tj ET", content)
        self.assertNotIn(b"({{version}}) Tj", content)
        _, docx = self.call("GET", f"/api/deliveries/{d['id']}/report.docx")
        with zipfile.ZipFile(io.BytesIO(docx)) as z:
            document = z.read("word/document.xml").decode()
        self.assertIn("Déployer 3.4.0 en recette", document)
        self.assertNotIn("Déployer {{version}}", document)
        req = urllib.request.Request(f"{self.base}/api/delivery-tasks/{task['id']}/tables.docx")
        with urllib.request.urlopen(req) as res:
            self.assertIn("D%C3%A9ployer_3.4.0_en_recette", res.headers["Content-Disposition"])

    def test_app_title_and_version(self):
        from delivery_app import __version__
        _, st = self.call("GET", "/api/settings")
        self.assertEqual((st["app_title"], st["app_version"], st["schema_version"]),
                         ("Checklist Livraison", __version__, dbmod.SCHEMA_VERSION))
        self.call("PUT", "/api/settings", {"default_variables": {"env": "prod"}})
        _, st = self.call("PUT", "/api/settings", {"app_title": "  Livraisons   ACME "})
        self.assertEqual(st["app_title"], "Livraisons ACME")
        self.assertEqual(st["default_variables"], {"env": "prod"})  # untouched by a title change
        _, d = self.call("POST", "/api/deliveries", {"version": "8.0.0"})
        status, pdf = self.call("GET", f"/api/deliveries/{d['id']}/report.pdf")
        self.assertEqual(status, 200)
        self.assertIn(b"(Livraisons ACME", pdf_content(pdf))
        _, docx = self.call("GET", f"/api/deliveries/{d['id']}/report.docx")
        with zipfile.ZipFile(io.BytesIO(docx)) as z:
            self.assertIn(f"Livraisons ACME {__version__}", z.read("word/document.xml").decode())
            self.assertIn("Livraisons ACME", z.read("docProps/core.xml").decode())
        _, st = self.call("PUT", "/api/settings", {"app_title": "   "})
        self.assertEqual(st["app_title"], "Checklist Livraison")

    def test_requests_from_other_sites_are_refused(self):
        self.assertEqual(self.call("POST", "/api/deliveries", {"version": "9"}, app=False)[0], 403)
        self.assertEqual(self.call("DELETE", "/api/tasks/1", app=False)[0], 403)
        self.assertEqual(self.call("GET", "/api/tasks", headers={"Host": "evil.example:8765"})[0], 403)
        self.assertEqual(self.call("GET", "/api/tasks", app=False)[0], 200)

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


def pdf_content(data):
    """Decompressed content streams of a PDF (where its text lives)."""
    return b"".join(zlib.decompress(m.group(1)) for m in
                    re.finditer(rb"<< /Filter /FlateDecode /Length \d+ >>\nstream\n(.*?)\nendstream", data, re.S))


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "delivery.db"
        self.db = Database(self.path)

    def tearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    def add_media(self, size, age_seconds):
        created = datetime.fromtimestamp(time.time() - age_seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db.conn:
            return self.db.conn.execute("INSERT INTO media (filename, mime, size, data, created_at) VALUES (?,?,?,?,?)",
                                        ("v.mp4", "video/mp4", size, os.urandom(size), created)).lastrowid

    def test_cleanup_gives_space_back_and_keeps_what_is_used(self):
        db = self.db
        tasks = db.list_template_tasks()
        used = self.add_media(300_000, 7200)
        db.update_template_task(tasks[0]["id"], {"blocks": tasks[0]["blocks"] + [{"type": "media", "files": [used]}]})
        d = db.create_delivery({"version": "1.0.0"})
        unused_old = self.add_media(2_000_000, 7200)  # removed from its task long ago
        fresh = self.add_media(50_000, 0)             # just uploaded, editor maybe still open
        # A comment whose task is gone (left by a database edited without foreign keys).
        db.conn.execute("PRAGMA foreign_keys = OFF")
        with db.conn:
            db.conn.execute("INSERT INTO comments (delivery_task_id, body, created_at) VALUES (999999, 'x', '2026-01-01T00:00:00Z')")
        db.conn.execute("PRAGMA foreign_keys = ON")
        # Deleting a big delivery capture leaves free pages: the file does not shrink by itself.
        with db.conn:
            db.conn.execute("INSERT INTO images (delivery_task_id, filename, mime, size, data, created_at) VALUES (?,?,?,?,?,?)",
                            (d["tasks"][0]["id"], "c.png", "image/png", 3_000_000, os.urandom(3_000_000), "2026-01-01T00:00:00Z"))
            db.conn.execute("DELETE FROM images")
        backup = self.path.with_name("delivery.db.v4-20260101-000000.bak")
        backup.write_bytes(b"x" * 1000)

        report = db.storage()
        self.assertEqual(report["reclaimable"]["unused_media"]["count"], 1)
        self.assertGreater(report["reclaimable"]["unused_media"]["bytes"], 1_900_000)
        self.assertEqual(report["reclaimable"]["orphans"]["count"], 1)
        self.assertGreater(report["reclaimable"]["free_bytes"], 2_500_000)
        self.assertEqual([b["name"] for b in report["backups"]], [backup.name])

        size_before = self.path.stat().st_size + report["journal_bytes"]
        result = db.cleanup()
        self.assertEqual((result["result"]["media"], result["result"]["rows"], result["result"]["backups"]), (1, 1, 0))
        self.assertLess(self.path.stat().st_size + result["journal_bytes"], size_before - 4_000_000)
        ids = {r[0] for r in db.conn.execute("SELECT id FROM media")}
        self.assertEqual(ids, {used, fresh})
        self.assertEqual(db.get_delivery(d["id"])["tasks"][0]["blocks"], db.list_template_tasks()[0]["blocks"])
        self.assertTrue(backup.exists())
        self.assertEqual(result["reclaimable"]["free_bytes"], 0)

        # Big deletions are compacted at the next start without any click.
        self.add_media(12_000_000, 3 * 86400)
        db.conn.close()
        self.db = db = Database(self.path)
        self.assertGreater(db.compacted_bytes, 11_000_000)
        self.assertEqual(db.storage()["reclaimable"]["free_bytes"], 0)

        result = db.cleanup(delete_backups=True)
        self.assertEqual(result["result"]["backups"], 1)
        self.assertFalse(backup.exists())
        self.assertEqual(result["backups"], [])


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

    def test_rich_note_markup(self):
        plain = frozenset()
        self.assertEqual(parse_inline("**gras** *it* __sou__ ~~bar~~"), [
            ("gras", {"b"}), (" ", plain), ("it", {"i"}), (" ", plain), ("sou", {"u"}), (" ", plain), ("bar", {"s"})])
        self.assertEqual(parse_inline("x **a *b* c** y")[2], ("b", {"b", "i"}))
        # Stars and underscores that are not formatting stay as typed.
        for text in ("rm *.log", "2 * 3 * 4", "{{prev_version}}", "prev__version", "\\*pas\\*"):
            self.assertEqual([t for t, st in parse_inline(text) if st], [], text)
        self.assertEqual(parse_inline("\\*pas\\*"), [("*pas*", plain)])
        blocks = parse_rich("Intro\nsuite\n\n- un\n* deux\n3. trois\n4) quatre\nfin **a\nb**")
        self.assertEqual([(b["kind"], len(b["items"])) for b in blocks], [("p", 1), ("list", 4), ("p", 1)])
        self.assertEqual([(i["kind"], i["number"]) for i in blocks[1]["items"]], [("ul", 1), ("ul", 2), ("ol", 3), ("ol", 4)])
        self.assertEqual(blocks[0]["items"][0], [("Intro", plain), ("\n", plain), ("suite", plain)])
        self.assertEqual(blocks[-1]["items"][0], [("fin **a", plain), ("\n", plain), ("b**", plain)])  # not across lines

    def test_nested_lists(self):
        (block,) = parse_rich("- a\n\t- a1\n\t\t1. x\n\t\t2. y\n    7. z\n- b\n\t\t\t- trop profond\n\t1. c")
        self.assertEqual([(i["level"], i["kind"], i["number"], i["segments"][0][0]) for i in block["items"]], [
            (0, "ul", 1, "a"), (1, "ul", 1, "a1"), (2, "ol", 1, "x"), (2, "ol", 2, "y"),
            (2, "ol", 3, "z"),           # two spaces per level, numbering continues in the same list
            (0, "ul", 2, "b"), (1, "ul", 1, "trop profond"),  # at most one level deeper than the line above
            (1, "ol", 1, "c")])          # new kind at that level: a new list starting at its typed number
        self.assertEqual(parse_rich("\t\t- seul")[0]["items"][0]["level"], 0)

    def test_variables_can_use_other_variables(self):
        variables = build_variables({"version": "2.4.1", "variables": {
            "url": "https://{{host}}/app/{{major}}/{{version}}",  # declared before what it uses
            "host": "{{env}}.example.com", "env": "recette",
            "loop_a": "a-{{loop_b}}", "loop_b": "b-{{loop_a}}", "self": "x{{self}}",
            "partial": "{{env}}/{{unknown}}/{{blank}}", "blank": ""}})
        self.assertEqual(variables["url"], "https://recette.example.com/app/2/2.4.1")
        self.assertEqual(render_command("curl {{url}}", variables), "curl https://recette.example.com/app/2/2.4.1")
        # Loops and unknown or empty references stay visible instead of hanging or vanishing.
        self.assertEqual((variables["loop_a"], variables["loop_b"]), ("a-b-{{loop_a}}", "b-a-{{loop_b}}"))
        self.assertEqual(variables["self"], "x{{self}}")
        self.assertEqual(variables["partial"], "recette/{{unknown}}/{{blank}}")
        # A delivery overriding one variable changes the ones built from it.
        self.assertEqual(build_variables({"version": "3.0.0", "variables": {"env": "prod", "host": "{{env}}.ex"}})["host"],
                         "prod.ex")


FIXTURES = Path(__file__).parent / "fixtures"
TABLES = ("settings", "template_tasks", "deliveries", "delivery_tasks", "comments")
FILE_TABLES = ("images", "template_images", "media")  # files may move between them, never vanish


def all_files(conn):
    """Every stored file (sorted bytes), whatever table holds it."""
    present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return sorted(bytes(r[0]) for t in FILE_TABLES if t in present for r in conn.execute(f"SELECT data FROM {t}"))


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
                    files = all_files(raw)
                    raw.close()

                    db = Database(path)
                    self.assertEqual(schema_of(db.conn), expected_schema)
                    for table, count in counts.items():
                        self.assertEqual(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], count, table)
                    self.assertEqual([tuple(r) for r in db.conn.execute("SELECT body FROM comments ORDER BY id")], comments)
                    self.assertEqual(all_files(db.conn), files)
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

    def test_older_contents_become_blocks(self):
        """v2 command + table, v3 lists and v4 reference screenshots all end up as blocks."""
        with tempfile.TemporaryDirectory() as tmp:
            for version in (2, 3, 4):
                path = load_fixture(version, tmp)
                raw = sqlite3.connect(str(path))
                if version == 2:
                    legacy = {r[0]: ([("command", r[1])] if r[1].strip() else []) + ([("table", r[2])] if r[2].strip() else [])
                              for r in raw.execute("SELECT id, command, table_spec FROM delivery_tasks")}
                else:
                    legacy = {r[0]: [("command", c["text"]) for c in json.loads(r[1])]
                              + [("table", t["spec"]) for t in json.loads(r[2])]
                              for r in raw.execute("SELECT id, commands, link_tables FROM delivery_tasks")}
                refs = (raw.execute("SELECT COUNT(*) FROM images WHERE reference=1").fetchone()[0]
                        if version == 4 else 0)
                raw.close()
                db = Database(path)
                media_files = 0
                for task_id, expected in legacy.items():
                    blocks = db.get_delivery_task(task_id)["blocks"]
                    content = [(b["type"], b["text"] if b["type"] == "command" else b["spec"])
                               for b in blocks if b["type"] in ("command", "table")]
                    self.assertEqual(content, expected, f"v{version} task {task_id}")
                    media_files += sum(len(b["files"]) for b in blocks if b["type"] == "media")
                self.assertEqual(media_files, refs)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM images WHERE reference=1").fetchone()[0], 0)
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
