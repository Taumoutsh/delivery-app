"""HTTP server (standard library only): JSON API + static frontend."""

import json
import mimetypes
import pkgutil
import re
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlparse

from . import report

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_UPLOAD = 15 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg"}  # the UI converts GIF/WebP to PNG before upload

ROUTES = []


def route(method, pattern):
    def register(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn
    return register


class HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def found(value):
    if value is None:
        raise HttpError(HTTPStatus.NOT_FOUND, "Élément introuvable.")
    return value


# -- settings & template ---------------------------------------------------

@route("GET", "/api/settings")
def get_settings(h):
    return h.db.get_settings()


@route("PUT", "/api/settings")
def put_settings(h):
    return h.db.save_settings(h.json())


@route("GET", "/api/tasks")
def list_tasks(h):
    return h.db.list_template_tasks()


@route("POST", "/api/tasks")
def create_task(h):
    return h.db.create_template_task(h.json())


@route("POST", "/api/tasks/reorder")
def reorder_tasks(h):
    return h.db.reorder_template_tasks(h.json().get("ids", []))


@route("PUT", r"/api/tasks/(\d+)")
def update_task(h, task_id):
    return found(h.db.update_template_task(int(task_id), h.json()))


@route("DELETE", r"/api/tasks/(\d+)")
def delete_task(h, task_id):
    found(h.db.delete_template_task(int(task_id)) or None)
    return {"ok": True}


# -- deliveries ------------------------------------------------------------

@route("GET", "/api/deliveries")
def list_deliveries(h):
    return h.db.list_deliveries()


@route("POST", "/api/deliveries")
def create_delivery(h):
    return h.db.create_delivery(h.json())


@route("GET", r"/api/deliveries/(\d+)")
def get_delivery(h, delivery_id):
    return found(h.db.get_delivery(int(delivery_id)))


@route("PUT", r"/api/deliveries/(\d+)")
def update_delivery(h, delivery_id):
    return found(h.db.update_delivery(int(delivery_id), h.json()))


@route("DELETE", r"/api/deliveries/(\d+)")
def delete_delivery(h, delivery_id):
    found(h.db.delete_delivery(int(delivery_id)) or None)
    return {"ok": True}


@route("POST", r"/api/deliveries/(\d+)/tasks")
def add_delivery_task(h, delivery_id):
    return found(h.db.add_delivery_task(int(delivery_id), h.json()))


@route("POST", r"/api/deliveries/(\d+)/reorder")
def reorder_delivery_tasks(h, delivery_id):
    return found(h.db.reorder_delivery_tasks(int(delivery_id), h.json().get("ids", [])))


@route("GET", r"/api/deliveries/(\d+)/report\.(pdf|docx)")
def export_report(h, delivery_id, fmt):
    delivery = found(h.db.get_delivery(int(delivery_id)))
    data = report.build_pdf(delivery, h.db) if fmt == "pdf" else report.build_docx(delivery, h.db)
    mime = "application/pdf" if fmt == "pdf" else DOCX_MIME
    safe = re.sub(r"[^\w.-]+", "_", delivery["version"])
    h.send_bytes(data, mime, f"livraison_{safe}.{fmt}", attachment=True)


@route("GET", r"/api/delivery-tasks/(\d+)/table\.docx")
def export_task_table(h, task_id):
    task = found(h.db.get_delivery_task(int(task_id)))
    delivery = found(h.db.get_delivery(task["delivery_id"]))
    data = report.build_table_docx(task, delivery)
    safe = re.sub(r"[^\w.-]+", "_", f"tableau_{task['title'][:40]}_{delivery['version']}")
    h.send_bytes(data, DOCX_MIME, f"{safe}.docx", attachment=True)


@route("PUT", r"/api/delivery-tasks/(\d+)")
def update_delivery_task(h, task_id):
    return found(h.db.update_delivery_task(int(task_id), h.json()))


@route("DELETE", r"/api/delivery-tasks/(\d+)")
def delete_delivery_task(h, task_id):
    return found(h.db.delete_delivery_task(int(task_id)))


@route("POST", r"/api/delivery-tasks/(\d+)/action")
def task_action(h, task_id):
    return found(h.db.task_action(int(task_id), h.json().get("action")))


@route("POST", r"/api/delivery-tasks/(\d+)/comments")
def add_comment(h, task_id):
    return found(h.db.add_comment(int(task_id), h.json().get("body")))


@route("DELETE", r"/api/comments/(\d+)")
def delete_comment(h, comment_id):
    return found(h.db.delete_comment(int(comment_id)))


@route("POST", r"/api/delivery-tasks/(\d+)/images")
def upload_image(h, task_id):
    mime = (h.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if mime not in IMAGE_TYPES:
        raise HttpError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Formats acceptés : PNG, JPEG.")
    filename = unquote(h.headers.get("X-Filename") or "image")[:200]
    return found(h.db.add_image(int(task_id), filename, mime, h.body()))


@route("GET", r"/api/images/(\d+)")
def get_image(h, image_id):
    img = found(h.db.get_image(int(image_id)))
    h.send_bytes(img["data"], img["mime"], img["filename"])


@route("DELETE", r"/api/images/(\d+)")
def delete_image(h, image_id):
    return found(h.db.delete_image(int(image_id)))


# -- handler ---------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    db = None  # injected by make_server
    server_version = "DeliveryChecklist/1.0"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            raise HttpError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Fichier trop volumineux (15 Mo max).")
        return self.rfile.read(length) if length else b""

    def json(self):
        raw = self.body()
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise HttpError(HTTPStatus.BAD_REQUEST, "JSON invalide.")

    def send_bytes(self, data, mime, filename=None, attachment=False):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            kind = "attachment" if attachment else "inline"
            self.send_header("Content-Disposition", f"{kind}; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def dispatch(self, method):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/"):
                for m, pattern, fn in ROUTES:
                    match = pattern.match(path)
                    if m == method and match:
                        result = fn(self, *match.groups())
                        if result is not None:
                            self.send_json(result)
                        return
                raise HttpError(HTTPStatus.NOT_FOUND, "Route inconnue.")
            if method != "GET":
                raise HttpError(HTTPStatus.METHOD_NOT_ALLOWED, "Méthode non autorisée.")
            self.serve_static(path)
        except HttpError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            traceback.print_exc()
            self.send_json({"error": "Erreur interne du serveur."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static(self, path):
        # pkgutil reads from the package directory or from inside a .pyz archive alike.
        rel = "index.html" if path in ("", "/") else unquote(path).lstrip("/")
        if any(part in ("", ".", "..") for part in rel.split("/")) or "\\" in rel:
            raise HttpError(HTTPStatus.NOT_FOUND, "Fichier introuvable.")
        try:
            data = pkgutil.get_data("delivery_app", f"static/{rel}")
        except (OSError, ValueError):
            data = None
        if data is None:
            raise HttpError(HTTPStatus.NOT_FOUND, "Fichier introuvable.")
        mime = mimetypes.guess_type(rel)[0] or ("font/woff2" if rel.endswith(".woff2") else "application/octet-stream")
        if mime.startswith("text/") or mime.endswith("javascript"):
            mime += "; charset=utf-8"
        self.send_bytes(data, mime)

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_DELETE(self):
        self.dispatch("DELETE")


def make_server(db, host, port):
    handler = type("BoundHandler", (Handler,), {"db": db})
    return ThreadingHTTPServer((host, port), handler)
