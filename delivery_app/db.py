"""SQLite storage: schema, migrations and data-access helpers."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import blocks as blockreg
from .templating import build_variables, render_command  # noqa: F401 (re-exported)

# Schema of a NEW database, always at the latest version. Existing databases are upgraded
# by MIGRATIONS below instead. Any change here needs a matching migration (see SPECS.md §3.2).
SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Master checklist: the tasks copied into every new delivery.
CREATE TABLE IF NOT EXISTS template_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    position          INTEGER NOT NULL DEFAULT 0,
    title             TEXT    NOT NULL,
    description       TEXT    NOT NULL DEFAULT '',
    blocks            TEXT    NOT NULL DEFAULT '[]', -- JSON content blocks, see blocks.py
    estimated_minutes INTEGER NOT NULL DEFAULT 0,    -- also the task's weight in the progress
    -- legacy columns, unused since v5 (kept so old databases and new ones stay identical):
    command           TEXT    NOT NULL DEFAULT '',
    table_spec        TEXT    NOT NULL DEFAULT '',
    commands          TEXT    NOT NULL DEFAULT '[]',
    link_tables       TEXT    NOT NULL DEFAULT '[]',
    weight            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    version      TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    variables    TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | done
    created_at   TEXT NOT NULL,
    completed_at TEXT
);

-- Snapshot of the template at delivery creation (history is never rewritten).
CREATE TABLE IF NOT EXISTS delivery_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id       INTEGER NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    template_task_id  INTEGER REFERENCES template_tasks(id) ON DELETE SET NULL,
    position          INTEGER NOT NULL DEFAULT 0,
    title             TEXT    NOT NULL,
    description       TEXT    NOT NULL DEFAULT '',
    blocks            TEXT    NOT NULL DEFAULT '[]', -- JSON content blocks, see blocks.py
    estimated_minutes INTEGER NOT NULL DEFAULT 0,    -- also the task's weight in the progress
    -- legacy columns, unused since v5 (kept so old databases and new ones stay identical):
    command           TEXT    NOT NULL DEFAULT '',
    table_spec        TEXT    NOT NULL DEFAULT '',
    commands          TEXT    NOT NULL DEFAULT '[]',
    link_tables       TEXT    NOT NULL DEFAULT '[]',
    weight            INTEGER NOT NULL DEFAULT 1,
    status            TEXT    NOT NULL DEFAULT 'todo', -- todo | running | paused | done | skipped
    elapsed_seconds   INTEGER NOT NULL DEFAULT 0,
    running_since     TEXT,
    started_at        TEXT,
    completed_at      TEXT
);

CREATE TABLE IF NOT EXISTS comments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_task_id INTEGER NOT NULL REFERENCES delivery_tasks(id) ON DELETE CASCADE,
    body             TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_task_id INTEGER NOT NULL REFERENCES delivery_tasks(id) ON DELETE CASCADE,
    filename         TEXT NOT NULL,
    mime             TEXT NOT NULL,
    size             INTEGER NOT NULL,
    data             BLOB NOT NULL,
    created_at       TEXT NOT NULL,
    reference        INTEGER NOT NULL DEFAULT 0  -- 1 = copied from the template task at creation
);

-- Files of "media" blocks (images, videos). Immutable and shared: a delivery created from the
-- template references the same rows, so the template can change without touching the history.
CREATE TABLE IF NOT EXISTS media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    filename   TEXT NOT NULL,
    mime       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    data       BLOB NOT NULL,
    created_at TEXT NOT NULL
);

-- Legacy (v4), emptied by the v5 migration: reference screenshots now live in media blocks.
CREATE TABLE IF NOT EXISTS template_images (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    template_task_id INTEGER NOT NULL REFERENCES template_tasks(id) ON DELETE CASCADE,
    filename         TEXT NOT NULL,
    mime             TEXT NOT NULL,
    size             INTEGER NOT NULL,
    data             BLOB NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dtasks_delivery ON delivery_tasks(delivery_id);
CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(delivery_task_id);
CREATE INDEX IF NOT EXISTS idx_images_task ON images(delivery_task_id);
CREATE INDEX IF NOT EXISTS idx_template_images_task ON template_images(template_task_id);
"""


def _migrate_v2(conn):
    """v2: optional link table for Word on tasks."""
    for table in ("template_tasks", "delivery_tasks"):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN table_spec TEXT NOT NULL DEFAULT ''")


def _migrate_v3(conn):
    """v3: several command blocks and several Word tables per task (JSON lists)."""
    for table in ("template_tasks", "delivery_tasks"):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN commands TEXT NOT NULL DEFAULT '[]'")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN link_tables TEXT NOT NULL DEFAULT '[]'")
        for task_id, command, spec in conn.execute(f"SELECT id, command, table_spec FROM {table}").fetchall():
            commands = [{"label": "", "text": command}] if command.strip() else []
            tables = [{"title": "", "spec": spec}] if spec.strip() else []
            conn.execute(f"UPDATE {table} SET commands=?, link_tables=? WHERE id=?",
                         (json.dumps(commands, ensure_ascii=False), json.dumps(tables, ensure_ascii=False), task_id))


def _migrate_v4(conn):
    """v4: reference screenshots on template tasks, copied into deliveries."""
    conn.execute("""CREATE TABLE template_images (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        template_task_id INTEGER NOT NULL REFERENCES template_tasks(id) ON DELETE CASCADE,
        filename         TEXT NOT NULL,
        mime             TEXT NOT NULL,
        size             INTEGER NOT NULL,
        data             BLOB NOT NULL,
        created_at       TEXT NOT NULL)""")
    conn.execute("CREATE INDEX idx_template_images_task ON template_images(template_task_id)")
    conn.execute("ALTER TABLE images ADD COLUMN reference INTEGER NOT NULL DEFAULT 0")


def _migrate_v5(conn):
    """v5: task content becomes an ordered list of typed blocks; files move to the media table.

    Commands and Word tables become blocks; template reference screenshots (template_images) and
    their copies in deliveries (images.reference = 1) become a "media" block.
    """
    conn.execute("""CREATE TABLE media (
        id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, mime TEXT NOT NULL,
        size INTEGER NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL)""")
    for table, images_sql, delete_sql in (
            ("template_tasks", "SELECT filename, mime, size, data, created_at FROM template_images"
                               " WHERE template_task_id=? ORDER BY id",
             "DELETE FROM template_images WHERE template_task_id=?"),
            ("delivery_tasks", "SELECT filename, mime, size, data, created_at FROM images"
                               " WHERE delivery_task_id=? AND reference=1 ORDER BY id",
             "DELETE FROM images WHERE delivery_task_id=? AND reference=1")):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN blocks TEXT NOT NULL DEFAULT '[]'")
        for task_id, commands, tables in conn.execute(f"SELECT id, commands, link_tables FROM {table}").fetchall():
            blocks = [{"type": "command", "label": c.get("label", ""), "text": c.get("text", "")}
                      for c in json.loads(commands or "[]")]
            blocks += [{"type": "table", "title": t.get("title", ""), "spec": t.get("spec", "")}
                       for t in json.loads(tables or "[]")]
            files = [conn.execute("INSERT INTO media (filename, mime, size, data, created_at) VALUES (?,?,?,?,?)",
                                  tuple(img)).lastrowid
                     for img in conn.execute(images_sql, (task_id,)).fetchall()]
            if files:
                blocks.append({"type": "media", "title": "Captures de référence", "files": files})
                conn.execute(delete_sql, (task_id,))
            conn.execute(f"UPDATE {table} SET blocks=? WHERE id=?",
                         (json.dumps(blockreg.normalize(blocks), ensure_ascii=False), task_id))


# version -> step upgrading a database from (version - 1). Steps run in order, in one transaction.
# Never edit a released step: add a new one.
MIGRATIONS = {
    2: _migrate_v2,
    3: _migrate_v3,
    4: _migrate_v4,
    5: _migrate_v5,
}
SCHEMA_VERSION = max(MIGRATIONS)


class SchemaTooNew(Exception):
    """The database was written by a more recent version of the app."""

# (title, description, estimated minutes, blocks) — examples to adapt.
SEED_TASKS = [
    ("Mettre à jour le numéro de version",
     "Mettre à jour le fichier de version et le changelog avant de créer la branche.", 10,
     [{"type": "command", "label": "", "text": 'git checkout develop && git pull\necho "{{version}}" > VERSION\n'
                                              'git commit -am "chore: bump version to {{version}}"'}]),
    ("Créer la branche de release", "La branche part de develop à jour.", 5,
     [{"type": "command", "label": "", "text": "git checkout -b release/{{version}}\ngit push -u origin release/{{version}}"}]),
    ("Lancer la suite de tests",
     "Tous les tests doivent passer. Joindre une capture du rapport en cas d'échec.", 30,
     [{"type": "command", "label": "Tests", "text": "make test"},
      {"type": "command", "label": "Qualité", "text": "make lint"},
      {"type": "link", "label": "Pipeline de la branche", "url": "https://ci.example.com/app/-/pipelines?ref=release/{{version}}"}]),
    ("Construire les artefacts", "Build de l'image et du paquet pour la version.", 20,
     [{"type": "command", "label": "Image Docker",
       "text": "docker build -t registry.local/app:{{version}} .\ndocker push registry.local/app:{{version}}"},
      {"type": "command", "label": "Paquet", "text": "make package VERSION={{version}}"}]),
    ("Tagger la version", "Tag annoté, comparé à la version précédente {{prev_version}}.", 5,
     [{"type": "command", "label": "Créer le tag",
       "text": 'git tag -a v{{version}} -m "Release {{version}}"\ngit push origin v{{version}}'},
      {"type": "command", "label": "Changements depuis {{prev_version}}",
       "text": "git log --oneline v{{prev_version}}..v{{version}}"}]),
    ("Déployer en recette", "Déployer puis vérifier que la recette répond avec la bonne version.", 25,
     [{"type": "note", "text": "Prévenir l'équipe support avant de lancer le déploiement de {{version}}."},
      {"type": "command", "label": "", "text": "./deploy.sh --env recette --version {{version}}"},
      {"type": "link", "label": "Santé de la recette", "url": "https://recette.example.com/health"}]),
    ("Rédiger les notes de version", "Résumé des changements depuis {{prev_version}}, à envoyer à l'équipe.", 20,
     [{"type": "table", "title": "Liens de la livraison", "spec":
       "Élément | Lien\n"
       "Notes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})\n"
       "Tag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})\n"
       "Comparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})"},
      {"type": "table", "title": "Livrables", "spec":
       "Livrable | Emplacement\n"
       "Image Docker | [registry.local/app:{{version}}](https://registry.local/harbor/projects/app/tags/{{version}})\n"
       "Paquet | [app-{{version}}.tar.gz](https://artifacts.example.com/app/{{version}}/app-{{version}}.tar.gz)"}]),
]

# Media files not referenced by any block are deleted after this delay (abandoned uploads).
MEDIA_GRACE_DAYS = 1


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def live_elapsed(task):
    elapsed = task["elapsed_seconds"]
    if task["status"] == "running" and task["running_since"]:
        delta = datetime.now(timezone.utc) - parse_iso(task["running_since"])
        elapsed += max(0, int(delta.total_seconds()))
    return elapsed


def weight_of(task):
    """A task weighs its estimated time; a task without estimate counts as 1 minute."""
    return max(1, task["estimated_minutes"] or 0)


def progress_of(tasks):
    """Progress in percent weighted by estimated time; skipped tasks leave the denominator."""
    total = sum(weight_of(t) for t in tasks if t["status"] != "skipped")
    done = sum(weight_of(t) for t in tasks if t["status"] == "done")
    return round(100 * done / total) if total else 0


class Database:
    def __init__(self, path):
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.backup_path = None
        try:
            self._migrate()
            self.collect_media()
        except Exception:
            self.conn.close()
            raise

    # -- infrastructure -------------------------------------------------

    def _migrate(self):
        with self._lock:
            has_settings = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
            if not has_settings:
                self._create_fresh()
                return
            row = self.conn.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
            version = int(row["value"]) if row else 1
            if version > SCHEMA_VERSION:
                raise SchemaTooNew(
                    f"La base {self.path} est au format v{version}, plus récent que cette application "
                    f"(v{SCHEMA_VERSION}). Utilisez une version plus récente de l'application.")
            if version == SCHEMA_VERSION:
                return
            self.backup_path = self._backup(version)
            self.conn.isolation_level = None  # manual transaction: all steps or none
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                for target in range(version + 1, SCHEMA_VERSION + 1):
                    MIGRATIONS[target](self.conn)
                self.conn.execute("INSERT OR REPLACE INTO settings VALUES ('schema_version', ?)",
                                  (str(SCHEMA_VERSION),))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
            finally:
                self.conn.isolation_level = ""

    def _create_fresh(self):
        with self.conn:
            self.conn.executescript(SCHEMA)
            self.conn.execute("INSERT INTO settings VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            self.conn.execute("INSERT INTO settings VALUES ('default_variables', ?)",
                              (json.dumps({"prev_version": ""}),))
            ts = now_iso()
            for pos, (title, desc, est, blocks) in enumerate(SEED_TASKS):
                fields = _task_fields({"title": title, "description": desc, "estimated_minutes": est, "blocks": blocks})
                self.conn.execute(
                    "INSERT INTO template_tasks (position, title, description, blocks, estimated_minutes,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?)", (pos, *fields, ts, ts))

    def _backup(self, version):
        """Copy the database next to itself before upgrading it (delivery.db.v1-20261020-154700.bak)."""
        if self.path == ":memory:":
            return None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = Path(self.path).with_name(f"{Path(self.path).name}.v{version}-{stamp}.bak")
        dest = sqlite3.connect(str(target))
        try:
            self.conn.backup(dest)
        finally:
            dest.close()
        return target

    def _all(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _one(self, sql, args=()):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    # -- settings -------------------------------------------------------

    def get_settings(self):
        with self._lock:
            row = self._one("SELECT value FROM settings WHERE key='default_variables'")
            return {"default_variables": json.loads(row["value"]) if row else {}}

    def save_settings(self, data):
        variables = {str(k): str(v) for k, v in (data.get("default_variables") or {}).items()}
        with self._lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO settings VALUES ('default_variables', ?)",
                              (json.dumps(variables),))
        return self.get_settings()

    # -- template tasks -------------------------------------------------

    def list_template_tasks(self):
        with self._lock:
            return self._tasks_out(self._all("SELECT * FROM template_tasks ORDER BY position, id"))

    def create_template_task(self, data):
        ts = now_iso()
        with self._lock, self.conn:
            pos = self.conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM template_tasks").fetchone()[0]
            cur = self.conn.execute(
                "INSERT INTO template_tasks (position, title, description, blocks, estimated_minutes,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?)", (pos, *_task_fields(data), ts, ts))
            return self._tasks_out([self._one("SELECT * FROM template_tasks WHERE id=?", (cur.lastrowid,))])[0]

    def update_template_task(self, task_id, data):
        with self._lock, self.conn:
            current = self._one("SELECT * FROM template_tasks WHERE id=?", (task_id,))
            if not current:
                return None
            merged = {**_task_out(current), **data}
            self.conn.execute(
                "UPDATE template_tasks SET title=?, description=?, blocks=?, estimated_minutes=?, updated_at=?"
                " WHERE id=?", (*_task_fields(merged), now_iso(), task_id))
            return self._tasks_out([self._one("SELECT * FROM template_tasks WHERE id=?", (task_id,))])[0]

    def delete_template_task(self, task_id):
        with self._lock, self.conn:
            return self.conn.execute("DELETE FROM template_tasks WHERE id=?", (task_id,)).rowcount > 0

    def reorder_template_tasks(self, ids):
        with self._lock, self.conn:
            for pos, task_id in enumerate(ids):
                self.conn.execute("UPDATE template_tasks SET position=? WHERE id=?", (pos, int(task_id)))
        return self.list_template_tasks()

    # -- deliveries -----------------------------------------------------

    def list_deliveries(self):
        with self._lock:
            deliveries = self._all("SELECT * FROM deliveries ORDER BY created_at DESC, id DESC")
            for d in deliveries:
                tasks = self._all("SELECT status, estimated_minutes, elapsed_seconds, running_since"
                                  " FROM delivery_tasks WHERE delivery_id=?", (d["id"],))
                d["variables"] = json.loads(d["variables"])
                d["progress"] = progress_of(tasks)
                d["task_count"] = len(tasks)
                d["done_count"] = sum(1 for t in tasks if t["status"] in ("done", "skipped"))
            return deliveries

    def create_delivery(self, data):
        version = str(data.get("version") or "").strip()
        if not version:
            raise ValueError("La version est obligatoire.")
        variables = {str(k): str(v) for k, v in (data.get("variables") or {}).items()}
        ts = now_iso()
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO deliveries (version, name, variables, created_at) VALUES (?,?,?,?)",
                (version, str(data.get("name") or "").strip(), json.dumps(variables), ts))
            delivery_id = cur.lastrowid
            for t in self._all("SELECT * FROM template_tasks ORDER BY position, id"):
                # The blocks are copied; their media files are immutable rows shared with the template.
                self.conn.execute(
                    "INSERT INTO delivery_tasks (delivery_id, template_task_id, position, title, description,"
                    " blocks, estimated_minutes) VALUES (?,?,?,?,?,?,?)",
                    (delivery_id, t["id"], t["position"], t["title"], t["description"], t["blocks"],
                     t["estimated_minutes"]))
        return self.get_delivery(delivery_id)

    def get_delivery(self, delivery_id):
        with self._lock:
            d = self._one("SELECT * FROM deliveries WHERE id=?", (delivery_id,))
            if not d:
                return None
            d["variables"] = json.loads(d["variables"])
            tasks = self._tasks_out(self._all(
                "SELECT * FROM delivery_tasks WHERE delivery_id=? ORDER BY position, id", (delivery_id,)))
            for t in tasks:
                t["comments"] = self._all(
                    "SELECT id, body, created_at FROM comments WHERE delivery_task_id=? ORDER BY id", (t["id"],))
                t["images"] = self._all(
                    "SELECT id, filename, mime, size, created_at FROM images WHERE delivery_task_id=? ORDER BY id",
                    (t["id"],))
                for img in t["images"]:
                    img["url"] = f"/api/images/{img['id']}"
            d["tasks"] = tasks
            d["progress"] = progress_of(tasks)
            return d

    def update_delivery(self, delivery_id, data):
        with self._lock, self.conn:
            d = self._one("SELECT * FROM deliveries WHERE id=?", (delivery_id,))
            if not d:
                return None
            version = str(data.get("version", d["version"])).strip() or d["version"]
            name = str(data.get("name", d["name"])).strip()
            variables = d["variables"]
            if "variables" in data:
                variables = json.dumps({str(k): str(v) for k, v in (data["variables"] or {}).items()})
            status, completed_at = d["status"], d["completed_at"]
            if data.get("status") in ("in_progress", "done") and data["status"] != status:
                status = data["status"]
                completed_at = now_iso() if status == "done" else None
            self.conn.execute(
                "UPDATE deliveries SET version=?, name=?, variables=?, status=?, completed_at=? WHERE id=?",
                (version, name, variables, status, completed_at, delivery_id))
        return self.get_delivery(delivery_id)

    def delete_delivery(self, delivery_id):
        with self._lock, self.conn:
            return self.conn.execute("DELETE FROM deliveries WHERE id=?", (delivery_id,)).rowcount > 0

    # -- delivery tasks -------------------------------------------------

    def _task(self, task_id):
        return self._one("SELECT * FROM delivery_tasks WHERE id=?", (task_id,))

    def get_delivery_task(self, task_id):
        with self._lock:
            task = self._task(task_id)
            return self._tasks_out([task])[0] if task else None

    def add_delivery_task(self, delivery_id, data):
        with self._lock, self.conn:
            if not self._one("SELECT id FROM deliveries WHERE id=?", (delivery_id,)):
                return None
            template_id = None
            if data.get("add_to_template"):
                template_id = self.create_template_task(data)["id"]
            pos = self.conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM delivery_tasks"
                                    " WHERE delivery_id=?", (delivery_id,)).fetchone()[0]
            self.conn.execute(
                "INSERT INTO delivery_tasks (delivery_id, template_task_id, position, title, description,"
                " blocks, estimated_minutes) VALUES (?,?,?,?,?,?,?)", (delivery_id, template_id, pos, *_task_fields(data)))
        return self.get_delivery(delivery_id)

    def update_delivery_task(self, task_id, data):
        with self._lock, self.conn:
            current = self._task(task_id)
            if not current:
                return None
            merged = {**_task_out(current), **data}
            self.conn.execute(
                "UPDATE delivery_tasks SET title=?, description=?, blocks=?, estimated_minutes=? WHERE id=?",
                (*_task_fields(merged), task_id))
        return self.get_delivery(current["delivery_id"])

    def delete_delivery_task(self, task_id):
        with self._lock, self.conn:
            current = self._task(task_id)
            if not current:
                return None
            self.conn.execute("DELETE FROM delivery_tasks WHERE id=?", (task_id,))
        return self.get_delivery(current["delivery_id"])

    def reorder_delivery_tasks(self, delivery_id, ids):
        with self._lock, self.conn:
            for pos, task_id in enumerate(ids):
                self.conn.execute("UPDATE delivery_tasks SET position=? WHERE id=? AND delivery_id=?",
                                  (pos, int(task_id), delivery_id))
        return self.get_delivery(delivery_id)

    def task_action(self, task_id, action):
        """Timer / status state machine: start, pause, done, skip, reopen, reset."""
        with self._lock, self.conn:
            t = self._task(task_id)
            if not t:
                return None
            ts = now_iso()
            elapsed = live_elapsed(t)
            if action == "start":
                if t["status"] not in ("running", "done", "skipped"):
                    t.update(status="running", running_since=ts, started_at=t["started_at"] or ts)
            elif action == "pause":
                if t["status"] == "running":
                    t.update(status="paused", running_since=None, elapsed_seconds=elapsed)
            elif action in ("done", "skip"):
                t.update(status="done" if action == "done" else "skipped", running_since=None,
                         elapsed_seconds=elapsed, completed_at=ts)
            elif action == "reopen":
                if t["status"] in ("done", "skipped"):
                    t.update(status="paused" if t["elapsed_seconds"] else "todo", completed_at=None)
            elif action == "reset":
                t.update(status="todo", running_since=None, elapsed_seconds=0, started_at=None, completed_at=None)
            else:
                raise ValueError(f"Action inconnue : {action}")
            self.conn.execute(
                "UPDATE delivery_tasks SET status=?, elapsed_seconds=?, running_since=?, started_at=?,"
                " completed_at=? WHERE id=?",
                (t["status"], t["elapsed_seconds"], t["running_since"], t["started_at"], t["completed_at"], task_id))
        return self.get_delivery(t["delivery_id"])

    # -- comments & images ---------------------------------------------

    def add_comment(self, task_id, body):
        body = (body or "").strip()
        if not body:
            raise ValueError("Le commentaire est vide.")
        with self._lock, self.conn:
            t = self._task(task_id)
            if not t:
                return None
            self.conn.execute("INSERT INTO comments (delivery_task_id, body, created_at) VALUES (?,?,?)",
                              (task_id, body, now_iso()))
        return self.get_delivery(t["delivery_id"])

    def delete_comment(self, comment_id):
        with self._lock, self.conn:
            row = self._one("SELECT t.delivery_id FROM comments c JOIN delivery_tasks t"
                            " ON t.id = c.delivery_task_id WHERE c.id=?", (comment_id,))
            if not row:
                return None
            self.conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
        return self.get_delivery(row["delivery_id"])

    def add_image(self, task_id, filename, mime, data):
        with self._lock, self.conn:
            t = self._task(task_id)
            if not t:
                return None
            self.conn.execute(
                "INSERT INTO images (delivery_task_id, filename, mime, size, data, created_at) VALUES (?,?,?,?,?,?)",
                (task_id, filename, mime, len(data), sqlite3.Binary(data), now_iso()))
        return self.get_delivery(t["delivery_id"])

    def get_image(self, image_id):
        with self._lock:
            return self._one("SELECT * FROM images WHERE id=?", (image_id,))

    def image_to_template(self, image_id):
        """Add a delivery screenshot to the template task it came from, in its first media block
        (created as "Captures de référence" if needed), for the next deliveries."""
        with self._lock, self.conn:
            row = self._one("SELECT i.*, t.template_task_id, t.delivery_id FROM images i JOIN delivery_tasks t"
                            " ON t.id = i.delivery_task_id WHERE i.id=?", (image_id,))
            if not row:
                return None
            tpl = row["template_task_id"] and self._one("SELECT * FROM template_tasks WHERE id=?",
                                                        (row["template_task_id"],))
            if not tpl:
                raise ValueError("Cette tâche ne provient pas du modèle (ou sa tâche modèle a été supprimée).")
            media_id = self._insert_media(row["filename"], row["mime"], row["data"])
            blocks = blockreg.normalize(json.loads(tpl["blocks"]))
            target = next((b for b in blocks if b["type"] == "media"), None)
            if target is None:
                target = {"id": blockreg.new_id(), "type": "media", "title": "Captures de référence", "files": []}
                blocks.append(target)
            target["files"].append(media_id)
            self.conn.execute("UPDATE template_tasks SET blocks=?, updated_at=? WHERE id=?",
                              (json.dumps(blocks, ensure_ascii=False), now_iso(), tpl["id"]))
        return self.get_delivery(row["delivery_id"])

    # -- media (files of media blocks) -----------------------------------

    def _insert_media(self, filename, mime, data):
        return self.conn.execute(
            "INSERT INTO media (filename, mime, size, data, created_at) VALUES (?,?,?,?,?)",
            (filename, mime, len(data), sqlite3.Binary(data), now_iso())).lastrowid

    def add_media(self, filename, mime, data):
        """Store a file for a media block; it is attached when the task is saved."""
        with self._lock, self.conn:
            media_id = self._insert_media(filename, mime, data)
        return self._media_info([media_id])[media_id]

    def get_media(self, media_id):
        with self._lock:
            return self._one("SELECT * FROM media WHERE id=?", (media_id,))

    def _media_info(self, ids):
        ids = list(ids)
        if not ids:
            return {}
        rows = self._all(f"SELECT id, filename, mime, size FROM media WHERE id IN ({','.join('?' * len(ids))})", ids)
        return {r["id"]: {**r, "url": f"/api/media/{r['id']}"} for r in rows}

    def _tasks_out(self, rows):
        """API shape of task rows, with the details of their media files."""
        tasks = [_task_out(r) for r in rows]
        info = self._media_info({i for t in tasks for i in blockreg.media_ids(t["blocks"])})
        for t in tasks:
            for b in t["blocks"]:
                if b["type"] == "media":
                    b["files"] = [info[i] for i in b["files"] if i in info]
        return tasks

    def collect_media(self):
        """Delete media no block references any more (abandoned uploads, removed files)."""
        with self._lock, self.conn:
            used = set()
            for table in ("template_tasks", "delivery_tasks"):
                for (raw,) in self.conn.execute(f"SELECT blocks FROM {table}").fetchall():
                    used.update(blockreg.media_ids(blockreg.normalize(json.loads(raw or "[]"))))
            cutoff = datetime.now(timezone.utc).timestamp() - MEDIA_GRACE_DAYS * 86400
            stale = [r["id"] for r in self._all("SELECT id, created_at FROM media")
                     if r["id"] not in used and parse_iso(r["created_at"]).timestamp() < cutoff]
            for media_id in stale:
                self.conn.execute("DELETE FROM media WHERE id=?", (media_id,))
            return len(stale)

    # -- programs ---------------------------------------------------------

    def program_of(self, task_id, block_id):
        """Program block of a delivery task with its variables resolved, or None."""
        with self._lock:
            task = self.get_delivery_task(task_id)
            if not task:
                return None
            block = next((b for b in task["blocks"] if b["id"] == block_id and b["type"] == "program"), None)
            if not block:
                return None
            variables = build_variables(self.get_delivery(task["delivery_id"]))
            return {k: render_command(block[k], variables) for k in ("name", "path", "args", "cwd")}

    def delete_image(self, image_id):
        with self._lock, self.conn:
            row = self._one("SELECT t.delivery_id FROM images i JOIN delivery_tasks t"
                            " ON t.id = i.delivery_task_id WHERE i.id=?", (image_id,))
            if not row:
                return None
            self.conn.execute("DELETE FROM images WHERE id=?", (image_id,))
        return self.get_delivery(row["delivery_id"])


def _task_out(task):
    """API shape of a task row: blocks decoded, legacy columns hidden."""
    task = dict(task)
    for legacy in ("command", "table_spec", "commands", "link_tables", "weight"):
        task.pop(legacy, None)
    raw = task.get("blocks")
    task["blocks"] = blockreg.normalize(json.loads(raw or "[]") if isinstance(raw, str) else raw)
    return task


def _task_fields(data):
    """Values for (title, description, blocks, estimated_minutes)."""
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("Le titre est obligatoire.")
    return (
        title,
        str(data.get("description") or ""),
        json.dumps(blockreg.normalize(data.get("blocks")), ensure_ascii=False),
        max(0, int(data.get("estimated_minutes") or 0)),
    )
