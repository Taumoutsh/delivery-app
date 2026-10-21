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

from . import __version__, launcher, report
from .db import DeliveryClosed
from .templating import build_variables, render_command

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_IMAGE = 15 * 1024 * 1024
MAX_VIDEO = 2 * 1024 ** 3  # streamed to the media folder, never held in memory
MAX_JSON = 2 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg"}  # the UI converts GIF/WebP/BMP to PNG before upload
# Any video/* is accepted and stored as is; the browser plays MP4, WebM, Ogg (and often MOV),
# other formats (AVI, WMV, MKV…) are offered for download from the viewer instead.
VIDEO_EXTENSIONS = {".mp4": "video/mp4", ".m4v": "video/x-m4v", ".webm": "video/webm", ".ogv": "video/ogg",
                    ".mov": "video/quicktime", ".avi": "video/x-msvideo", ".wmv": "video/x-ms-wmv",
                    ".mkv": "video/x-matroska", ".mpg": "video/mpeg", ".mpeg": "video/mpeg", ".3gp": "video/3gpp"}
# Header every API call of the UI sends. A web page from another site cannot add it without a CORS
# preflight, which this server never grants: it protects state changes and program launches.
CSRF_HEADER = "X-Checklist"

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


@route("GET", "/api/storage")
def get_storage(h):
    return h.db.storage()


@route("POST", "/api/storage/cleanup")
def cleanup_storage(h):
    return h.db.cleanup(delete_backups=bool(h.json().get("delete_backups")))


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


@route("GET", r"/api/delivery-tasks/(\d+)/tables?\.docx")
def export_task_tables(h, task_id):
    """Every Word table of the task, each preceded by its title (table.docx kept for v1.2 links)."""
    send_task_tables(h, int(task_id), None)


@route("GET", r"/api/delivery-tasks/(\d+)/tables/([\w-]+)\.docx")
def export_task_table(h, task_id, block_id):
    send_task_tables(h, int(task_id), block_id)


def send_task_tables(h, task_id, block_id):
    task = found(h.db.get_delivery_task(task_id))
    delivery = found(h.db.get_delivery(task["delivery_id"]))
    data = report.build_table_docx(task, delivery, block_id)
    block = next((b for b in task["blocks"] if b["id"] == block_id), None)
    name = render_command((block and block.get("title")) or task["title"], build_variables(delivery))
    safe = re.sub(r"[^\w.-]+", "_", f"tableau_{name[:40]}_{delivery['version']}")
    h.send_bytes(data, DOCX_MIME, f"{safe}.docx", attachment=True)


@route("POST", r"/api/delivery-tasks/(\d+)/blocks/([\w-]+)/launch")
def launch_program(h, task_id, block_id):
    if not h.allow_launch:
        raise HttpError(HTTPStatus.FORBIDDEN, "Le lancement de programmes est désactivé (option --no-launch).")
    program = found(h.db.program_of(int(task_id), block_id))
    try:
        started = launcher.launch(program)
    except launcher.LaunchError as exc:
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
    sys.stderr.write(f"Programme lancé : {started}\n")
    return {"message": f"« {program['name'] or program['path']} » lancé."}


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


def uploaded_file(h, videos=False):
    """(filename, mime, data) of a raw file upload: PNG/JPEG images, and any video when videos=True
    (for a video, data is None: the caller streams the body, see upload_media).

    Browsers send no type (or application/octet-stream) for some files, e.g. .mkv on Windows:
    the type is then deduced from the file name.
    """
    filename = unquote(h.headers.get("X-Filename") or "fichier")[:200]
    mime = (h.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if mime in ("", "application/octet-stream"):
        suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        mime = VIDEO_EXTENSIONS.get(suffix) or mimetypes.guess_type(filename)[0] or mime
    is_video = mime.startswith("video/")
    if mime not in IMAGE_TYPES and not (videos and is_video):
        accepted = "images PNG ou JPEG" + (" et vidéos (MP4, WebM, MOV, AVI, MKV…)" if videos else "")
        raise HttpError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                        f"Format non pris en charge pour « {filename} » ({mime or 'type inconnu'}) : {accepted}.")
    if is_video:
        h.check_length(MAX_VIDEO)
        return filename, mime, None
    return filename, mime, h.body(MAX_IMAGE)


@route("POST", r"/api/delivery-tasks/(\d+)/images")
def upload_image(h, task_id):
    return found(h.db.add_image(int(task_id), *uploaded_file(h)))


@route("POST", r"/api/images/(\d+)/to-template")
def image_to_template(h, image_id):
    return found(h.db.image_to_template(int(image_id)))


@route("POST", r"/api/media")
def upload_media(h):
    """File of a media block (image or video), attached when the task is saved."""
    filename, mime, data = uploaded_file(h, videos=True)
    if data is None:  # video: written to the media folder as it arrives
        return h.db.store_video(filename, mime, h.rfile, h.check_length(MAX_VIDEO))
    return h.db.add_media(filename, mime, data)


@route("GET", r"/api/media/(\d+)")
def get_media(h, media_id):
    item = found(h.db.get_media(int(media_id)))
    if item["path"]:
        if not item["path"].is_file():
            raise HttpError(HTTPStatus.NOT_FOUND, f"Fichier introuvable dans le dossier media : {item['file']}")
        h.send_file(item["path"], item["mime"], item["filename"])
    else:
        h.send_bytes(item["data"], item["mime"], item["filename"], ranges=True)


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
    allow_launch = True
    allowed_hosts = frozenset()
    server_version = f"DeliveryChecklist/{__version__}"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    def check_length(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            size = f"{limit // 1024 ** 3} Go" if limit >= 1024 ** 3 else f"{limit // 1024 ** 2} Mo"
            raise HttpError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"Fichier trop volumineux ({size} maximum).")
        return length

    def body(self, limit=MAX_JSON):
        length = self.check_length(limit)
        return self.rfile.read(length) if length else b""

    def json(self):
        raw = self.body()
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise HttpError(HTTPStatus.BAD_REQUEST, "JSON invalide.")

    def _range(self, total):
        """(status, start, end) for the request's "Range: bytes=a-b" header (a single range), or
        None after answering 416 when it cannot be satisfied."""
        match = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if not (match and (match.group(1) or match.group(2))):
            return HTTPStatus.OK, 0, total - 1
        if match.group(1):
            start = int(match.group(1))
            end = min(int(match.group(2)), total - 1) if match.group(2) else total - 1
        else:
            start, end = max(0, total - int(match.group(2))), total - 1
        if start > end or start >= total:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{total}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        return HTTPStatus.PARTIAL_CONTENT, start, end

    def _file_headers(self, status, mime, length, total, start, end, filename, attachment, ranges):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        if ranges:
            self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        if filename:
            kind = "attachment" if attachment else "inline"
            self.send_header("Content-Disposition", f"{kind}; filename*=UTF-8''{quote(filename)}")
        self.end_headers()

    def send_bytes(self, data, mime, filename=None, attachment=False, ranges=False):
        """Send a file; with ranges=True a single "Range: bytes=a-b" is honoured (video seeking)."""
        total = len(data)
        status, start, end = HTTPStatus.OK, 0, total - 1
        if ranges:
            answer = self._range(total)
            if answer is None:
                return
            status, start, end = answer
        if status == HTTPStatus.PARTIAL_CONTENT:
            data = data[start:end + 1]
        self._file_headers(status, mime, len(data), total, start, end, filename, attachment, ranges)
        self.wfile.write(data)

    def send_file(self, path, mime, filename=None):
        """Stream a file from disk by chunks, honouring a Range header (video seeking)."""
        total = path.stat().st_size
        answer = self._range(total)
        if answer is None:
            return
        status, start, end = answer
        length = max(0, end - start + 1)
        self._file_headers(status, mime, length, total, start, end, filename, False, True)
        with open(path, "rb") as f:
            f.seek(start)
            while length > 0:
                chunk = f.read(min(1024 * 1024, length))
                if not chunk:
                    break
                self.wfile.write(chunk)
                length -= len(chunk)

    def check_request(self, method):
        """Refuse API calls from other sites: unknown Host (DNS rebinding) or, for any state change,
        a missing app header (cross-site request)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in self.allowed_hosts:
            raise HttpError(HTTPStatus.FORBIDDEN, "Hôte non autorisé.")
        if method != "GET" and self.headers.get(CSRF_HEADER) != "1":
            raise HttpError(HTTPStatus.FORBIDDEN, "Requête refusée : elle ne vient pas de l'application.")

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
                self.check_request(method)
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
        except DeliveryClosed as exc:
            self.send_json({"error": str(exc), "closed": True}, HTTPStatus.CONFLICT)
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


def make_server(db, host, port, allow_launch=True):
    hosts = {"localhost", "127.0.0.1", "::1"}
    if host not in ("0.0.0.0", "::", ""):
        hosts.add(host.lower())
    handler = type("BoundHandler", (Handler,), {
        "db": db, "allow_launch": allow_launch, "allowed_hosts": frozenset(hosts)})
    return ThreadingHTTPServer((host, port), handler)
