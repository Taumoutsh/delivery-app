"""Delivery reports (PDF and Word) and per-task Word tables, standard library only.

Task content blocks are rendered by DOCX_RENDERERS / PDF_RENDERERS (one function per block type,
see blocks.py); a type without renderer is simply left out of the reports.
"""

from datetime import datetime, timezone

from . import __version__
from . import pdf_writer as pdf
from .db import live_elapsed
from .docx_writer import Docx
from .templating import build_variables, parse_table, render_command

STATUS_LABELS = {
    "todo": "À faire",
    "running": "En cours",
    "paused": "En pause",
    "done": "Validée",
    "skipped": "Non applicable",
}


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h} h {m:02d}" if h else f"{m} min"


def fmt_date(iso):
    if not iso:
        return "—"
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
    return dt.strftime("%d/%m/%Y %H:%M")


def _summary(delivery):
    tasks = delivery["tasks"]
    done = sum(1 for t in tasks if t["status"] == "done")
    skipped = sum(1 for t in tasks if t["status"] == "skipped")
    estimated = sum(t["estimated_minutes"] for t in tasks if t["status"] != "skipped") * 60
    spent = sum(live_elapsed(t) for t in tasks)
    info = [
        ("Statut", "Clôturée" if delivery["status"] == "done" else "En cours"),
        ("Créée le", fmt_date(delivery["created_at"])),
        ("Clôturée le", fmt_date(delivery["completed_at"])),
        ("Progression", f"{delivery['progress']} % (pondérée)"),
        ("Tâches", f"{done} validées, {skipped} non applicables, {len(tasks)} au total"),
        ("Temps", f"{fmt_duration(spent)} passé / {fmt_duration(estimated)} estimé"),
    ]
    info += [(f"{{{{{k}}}}}", v) for k, v in delivery["variables"].items()]
    return build_variables(delivery), info


def _app_label(db):
    """« <titre de l'application> <version> », shown on every report."""
    return f"{db.app_title()} {__version__}"


def _task_meta(t):
    return (f"{STATUS_LABELS.get(t['status'], t['status'])} · "
            f"estimé {fmt_duration(t['estimated_minutes'] * 60)} · passé {fmt_duration(live_elapsed(t))} · "
            f"démarrée {fmt_date(t['started_at'])} · terminée {fmt_date(t['completed_at'])}")


# -- Word -------------------------------------------------------------------

def _docx_table(doc, table):
    rows = [[doc.segments(cell, bold=True, color="FFFFFF") for cell in table["headers"]]]
    rows += [[doc.segments(cell) for cell in row] for row in table["rows"]]
    doc.table(rows)


def build_docx(delivery, db):
    variables, info = _summary(delivery)
    app = _app_label(db)
    doc = Docx(f"Livraison {delivery['version']}", creator=app)
    doc.paragraph(doc.run(app, color="55606E", size=9))
    doc.heading(f"Rapport de livraison — {delivery['version']}", 0)
    if delivery["name"]:
        doc.paragraph(doc.run(delivery["name"], italic=True, color="55606E"))
    doc.table([[doc.run(k, bold=True), doc.run(v)] for k, v in info], header=False, widths=[1, 3])

    doc.heading("Synthèse", 1)
    rows = [[doc.run(h, bold=True, color="FFFFFF") for h in ("#", "Tâche", "Statut", "Estimé", "Passé")]]
    for i, t in enumerate(delivery["tasks"], 1):
        rows.append([doc.run(str(i)), doc.run(render_command(t["title"], variables)), doc.run(STATUS_LABELS.get(t["status"], t["status"])),
                     doc.run(fmt_duration(t["estimated_minutes"] * 60)), doc.run(fmt_duration(live_elapsed(t)))])
    doc.table(rows, widths=[0.5, 5, 1.8, 1.2, 1.2])

    doc.heading("Détail des tâches", 1)
    for i, t in enumerate(delivery["tasks"], 1):
        doc.heading(f"{i}. {render_command(t['title'], variables)}", 2)
        doc.paragraph(doc.run(_task_meta(t), color="55606E", size=9))
        if t["description"]:
            doc.paragraph(doc.run(render_command(t["description"], variables)))
        for block in t["blocks"]:
            render = DOCX_RENDERERS.get(block["type"])
            if render:
                render(doc, block, variables, db)
        for c in t["comments"]:
            doc.paragraph(doc.run(f"{fmt_date(c['created_at'])} — ", bold=True) + doc.run(c["body"]))
        for img in t["images"]:
            blob = db.get_image(img["id"])
            if doc.image(blob["data"], img["filename"]):
                doc.paragraph(doc.run(img["filename"], italic=True, color="55606E", size=8.5))
            else:
                doc.paragraph(doc.run(f"[image non intégrable : {img['filename']}]", italic=True))
    return doc.to_bytes()


def _docx_label(doc, text, variables, size=9):
    if text:
        doc.paragraph(doc.run(render_command(text, variables), bold=True, size=size), keep_next=True, after=0)


def _docx_command(doc, b, variables, db):
    _docx_label(doc, b["label"], variables)
    doc.code(render_command(b["text"], variables))


def _docx_link(doc, b, variables, db):
    url = render_command(b["url"], variables)
    label = render_command(b["label"], variables) or url
    doc.paragraph(doc.run("Lien : ", bold=True) + doc.link(label, url) + (doc.run(f"  ({url})", color="55606E", size=9)
                                                                           if b["label"] else ""))


def _docx_program(doc, b, variables, db):
    name = render_command(b["name"], variables) or "Programme"
    line = " ".join(x for x in (render_command(b["path"], variables), render_command(b["args"], variables)) if x)
    doc.paragraph(doc.run(f"Programme : {name}", bold=True), keep_next=True, after=0)
    doc.code(line)


def _docx_table_block(doc, b, variables, db):
    table = parse_table(b["spec"], variables)
    if table:
        if b["title"]:
            doc.paragraph(doc.run(render_command(b["title"], variables), bold=True), keep_next=True, after=60)
        _docx_table(doc, table)


def _docx_media(doc, b, variables, db):
    _docx_label(doc, b["title"], variables, size=10)
    for f in b["files"]:
        item = db.get_media(f["id"])
        if item and item["mime"].startswith("image/") and doc.image(item["data"], f["filename"]):
            doc.paragraph(doc.run(f["filename"], italic=True, color="55606E", size=8.5))
        else:
            kind = "Vidéo" if f["mime"].startswith("video/") else "Fichier"
            doc.paragraph(doc.run(f"[{kind} : {f['filename']} — à consulter dans l'application]", italic=True))


def _docx_note(doc, b, variables, db):
    doc.paragraph(doc.run(render_command(b["text"], variables)), style="Code")


DOCX_RENDERERS = {
    "command": _docx_command,
    "link": _docx_link,
    "program": _docx_program,
    "table": _docx_table_block,
    "media": _docx_media,
    "note": _docx_note,
}


def _tables(task, variables, block_id=None):
    """[(rendered title, parsed table)] for the task's Word table blocks (or the one with block_id)."""
    out = []
    for b in task["blocks"]:
        if b["type"] != "table" or (block_id is not None and b["id"] != block_id):
            continue
        table = parse_table(b["spec"], variables)
        if table:
            out.append((render_command(b["title"], variables), table))
    return out


def build_table_docx(task, delivery, block_id=None):
    """A .docx holding only the task's Word tables (or the block_id one), ready to insert elsewhere.

    With several tables each one is preceded by its title.
    """
    variables = build_variables(delivery)
    tables = _tables(task, variables, block_id)
    if not tables:
        raise ValueError("Tableau introuvable." if block_id else "Cette tâche n'a pas de tableau.")
    doc = Docx(render_command(task["title"], variables))
    for title, table in tables:
        if title and len(tables) > 1:
            doc.paragraph(doc.run(title, bold=True), keep_next=True, after=60)
        _docx_table(doc, table)
    return doc.to_bytes()


# -- PDF --------------------------------------------------------------------

def _pdf_cell(segments, font=pdf.REGULAR):
    return [(text, font, pdf.LINK if url else pdf.INK, url) for text, url in segments]


def _pdf_label(doc, text, variables, size=8.5, keep=40):
    if text:
        doc.ensure(keep)  # keep the label with what follows
        doc.text(render_command(text, variables), pdf.BOLD, size, after=0)


def _pdf_command(doc, b, variables, db):
    _pdf_label(doc, b["label"], variables)
    doc.code(render_command(b["text"], variables))


def _pdf_link(doc, b, variables, db):
    url = render_command(b["url"], variables)
    label = render_command(b["label"], variables) or url
    segments = [("Lien : ", pdf.BOLD, pdf.INK, None), (label, pdf.REGULAR, pdf.LINK, url)]
    if b["label"]:
        segments.append((f"  ({url})", pdf.REGULAR, pdf.MUTED, None))
    doc.rich(segments, size=9.5)


def _pdf_program(doc, b, variables, db):
    name = render_command(b["name"], variables) or "Programme"
    line = " ".join(x for x in (render_command(b["path"], variables), render_command(b["args"], variables)) if x)
    _pdf_label(doc, f"Programme : {name}", {}, size=9)
    doc.code(line)


def _pdf_table_block(doc, b, variables, db):
    table = parse_table(b["spec"], variables)
    if table:
        _pdf_label(doc, b["title"], variables, size=9.5, keep=70)
        doc.table([[_pdf_cell(c) for c in table["headers"]]] + [[_pdf_cell(c) for c in r] for r in table["rows"]])


def _pdf_media(doc, b, variables, db):
    _pdf_label(doc, b["title"], variables, size=9.5, keep=120)
    for f in b["files"]:
        item = db.get_media(f["id"])
        try:
            if not item or not item["mime"].startswith("image/"):
                raise pdf.Unsupported(item["mime"] if item else "absent")
            doc.image(item["data"], cache_key=("media", f["id"]))
            doc.text(f["filename"], pdf.ITALIC, 8, pdf.MUTED)
        except Exception:
            kind = "Vidéo" if f["mime"].startswith("video/") else "Fichier"
            doc.text(f"[{kind} : {f['filename']} — à consulter dans l'application]", pdf.ITALIC, 8.5, pdf.MUTED)


def _pdf_note(doc, b, variables, db):
    doc.text(render_command(b["text"], variables), pdf.ITALIC, 9.5)


PDF_RENDERERS = {
    "command": _pdf_command,
    "link": _pdf_link,
    "program": _pdf_program,
    "table": _pdf_table_block,
    "media": _pdf_media,
    "note": _pdf_note,
}


def build_pdf(delivery, db):
    variables, info = _summary(delivery)
    app = _app_label(db)
    doc = pdf.Pdf(title=f"Livraison {delivery['version']}", footer=f"{app} · Rapport de livraison {delivery['version']}")
    doc.text(app, size=8.5, color=pdf.MUTED, after=2)
    doc.text(f"Rapport de livraison — {delivery['version']}", pdf.BOLD, 20, after=4)
    if delivery["name"]:
        doc.text(delivery["name"], pdf.ITALIC, 11, pdf.MUTED, after=8)
    doc.space(6)
    doc.table([[[(k, pdf.BOLD, pdf.INK, None)], [(v, pdf.REGULAR, pdf.INK, None)]] for k, v in info],
              widths=[1, 3], header=False, size=9, zebra=False)

    doc.heading("Synthèse", 14, pdf.ACCENT)
    rows = [[[(h, pdf.BOLD, pdf.WHITE, None)] for h in ("#", "Tâche", "Statut", "Estimé", "Passé")]]
    for i, t in enumerate(delivery["tasks"], 1):
        rows.append([[(v, pdf.REGULAR, pdf.INK, None)] for v in (
            str(i), render_command(t["title"], variables), STATUS_LABELS.get(t["status"], t["status"]),
            fmt_duration(t["estimated_minutes"] * 60), fmt_duration(live_elapsed(t)))])
    doc.table(rows, widths=[0.5, 5, 1.8, 1.2, 1.2], size=9)

    doc.heading("Détail des tâches", 14, pdf.ACCENT)
    for i, t in enumerate(delivery["tasks"], 1):
        doc.heading(f"{i}. {render_command(t['title'], variables)}", 11.5, before=8, after=2)
        doc.text(_task_meta(t), size=8, color=pdf.MUTED, after=5)
        if t["description"]:
            doc.text(render_command(t["description"], variables), size=9.5)
        for block in t["blocks"]:
            render = PDF_RENDERERS.get(block["type"])
            if render:
                render(doc, block, variables, db)
        for c in t["comments"]:
            doc.rich([(f"{fmt_date(c['created_at'])} — ", pdf.BOLD, pdf.INK, None),
                      (c["body"], pdf.REGULAR, pdf.INK, None)], size=9.5)
        for img in t["images"]:
            blob = db.get_image(img["id"])
            try:
                doc.image(blob["data"], cache_key=("image", img["id"]))
                doc.text(img["filename"], pdf.ITALIC, 8, pdf.MUTED)
            except Exception:
                doc.text(f"[image non intégrable : {img['filename']}]", pdf.ITALIC, 8.5, pdf.MUTED)
        doc.space(6)
    return doc.to_bytes()
