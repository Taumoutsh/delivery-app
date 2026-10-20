"""Delivery reports (PDF and Word) and per-task link tables, standard library only."""

from datetime import datetime, timezone

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


def _task_meta(t):
    return (f"{STATUS_LABELS.get(t['status'], t['status'])} · poids {t['weight']} · "
            f"estimé {fmt_duration(t['estimated_minutes'] * 60)} · passé {fmt_duration(live_elapsed(t))} · "
            f"démarrée {fmt_date(t['started_at'])} · terminée {fmt_date(t['completed_at'])}")


# -- Word -------------------------------------------------------------------

def _docx_table(doc, table):
    rows = [[doc.segments(cell, bold=True, color="FFFFFF") for cell in table["headers"]]]
    rows += [[doc.segments(cell) for cell in row] for row in table["rows"]]
    doc.table(rows)


def build_docx(delivery, db):
    variables, info = _summary(delivery)
    doc = Docx(f"Livraison {delivery['version']}")
    doc.heading(f"Rapport de livraison — {delivery['version']}", 0)
    if delivery["name"]:
        doc.paragraph(doc.run(delivery["name"], italic=True, color="55606E"))
    doc.table([[doc.run(k, bold=True), doc.run(v)] for k, v in info], header=False, widths=[1, 3])

    doc.heading("Synthèse", 1)
    rows = [[doc.run(h, bold=True, color="FFFFFF") for h in ("#", "Tâche", "Statut", "Estimé", "Passé")]]
    for i, t in enumerate(delivery["tasks"], 1):
        rows.append([doc.run(str(i)), doc.run(t["title"]), doc.run(STATUS_LABELS.get(t["status"], t["status"])),
                     doc.run(fmt_duration(t["estimated_minutes"] * 60)), doc.run(fmt_duration(live_elapsed(t)))])
    doc.table(rows, widths=[0.5, 5, 1.8, 1.2, 1.2])

    doc.heading("Détail des tâches", 1)
    for i, t in enumerate(delivery["tasks"], 1):
        doc.heading(f"{i}. {t['title']}", 2)
        doc.paragraph(doc.run(_task_meta(t), color="55606E", size=9))
        if t["description"]:
            doc.paragraph(doc.run(render_command(t["description"], variables)))
        if t["command"]:
            doc.code(render_command(t["command"], variables))
        table = parse_table(t.get("table_spec"), variables)
        if table:
            _docx_table(doc, table)
        for c in t["comments"]:
            doc.paragraph(doc.run(f"{fmt_date(c['created_at'])} — ", bold=True) + doc.run(c["body"]))
        for img in t["images"]:
            blob = db.get_image(img["id"])
            if doc.image(blob["data"], img["filename"]):
                doc.paragraph(doc.run(img["filename"], italic=True, color="55606E", size=8.5))
            else:
                doc.paragraph(doc.run(f"[image non intégrable : {img['filename']}]", italic=True))
    return doc.to_bytes()


def build_table_docx(task, delivery):
    """A .docx holding only the task's link table, ready to insert into another document."""
    table = parse_table(task.get("table_spec"), build_variables(delivery))
    if not table:
        raise ValueError("Cette tâche n'a pas de tableau.")
    doc = Docx(task["title"])
    _docx_table(doc, table)
    return doc.to_bytes()


# -- PDF --------------------------------------------------------------------

def _pdf_cell(segments, font=pdf.REGULAR):
    return [(text, font, pdf.LINK if url else pdf.INK, url) for text, url in segments]


def build_pdf(delivery, db):
    variables, info = _summary(delivery)
    doc = pdf.Pdf(title=f"Livraison {delivery['version']}", footer=f"Rapport de livraison {delivery['version']}")
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
            str(i), t["title"], STATUS_LABELS.get(t["status"], t["status"]),
            fmt_duration(t["estimated_minutes"] * 60), fmt_duration(live_elapsed(t)))])
    doc.table(rows, widths=[0.5, 5, 1.8, 1.2, 1.2], size=9)

    doc.heading("Détail des tâches", 14, pdf.ACCENT)
    for i, t in enumerate(delivery["tasks"], 1):
        doc.heading(f"{i}. {t['title']}", 11.5, before=8, after=2)
        doc.text(_task_meta(t), size=8, color=pdf.MUTED, after=5)
        if t["description"]:
            doc.text(render_command(t["description"], variables), size=9.5)
        if t["command"]:
            doc.code(render_command(t["command"], variables))
        table = parse_table(t.get("table_spec"), variables)
        if table:
            doc.table([[_pdf_cell(c) for c in table["headers"]]] + [[_pdf_cell(c) for c in r] for r in table["rows"]])
        for c in t["comments"]:
            doc.rich([(f"{fmt_date(c['created_at'])} — ", pdf.BOLD, pdf.INK, None),
                      (c["body"], pdf.REGULAR, pdf.INK, None)], size=9.5)
        for img in t["images"]:
            blob = db.get_image(img["id"])
            try:
                doc.image(blob["data"], cache_key=img["id"])
                doc.text(img["filename"], pdf.ITALIC, 8, pdf.MUTED)
            except Exception:
                doc.text(f"[image non intégrable : {img['filename']}]", pdf.ITALIC, 8.5, pdf.MUTED)
        doc.space(6)
    return doc.to_bytes()
