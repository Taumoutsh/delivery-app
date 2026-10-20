"""End-to-end API tests against a real server on a temporary database.

Run: python -m unittest discover tests
"""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from delivery_app.db import Database, build_variables, render_command
from delivery_app.server import make_server

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

    def test_validation_errors(self):
        status, body = self.call("POST", "/api/deliveries", {"version": "  "})
        self.assertEqual(status, 400)
        self.assertIn("version", body["error"])
        status, _ = self.call("POST", "/api/delivery-tasks/1/images", raw=b"x",
                              headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _ = self.call("GET", "/api/deliveries/99999")
        self.assertEqual(status, 404)


class RenderTest(unittest.TestCase):
    def test_variables(self):
        variables = build_variables({"version": "2.4.1", "name": "x", "created_at": "2026-01-02T10:00:00Z",
                                     "variables": {"env": "prod"}})
        self.assertEqual(render_command("v{{version}} {{ major }}.{{minor}} {{env}} {{unknown}}", variables),
                         "v2.4.1 2.4 prod {{unknown}}")
        self.assertEqual(variables["date"], "2026-01-02")


if __name__ == "__main__":
    unittest.main()
