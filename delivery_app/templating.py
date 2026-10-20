"""Variable substitution and link-table parsing (mirrored in static/app.js)."""

import re
from datetime import datetime, timezone

_PLACEHOLDER = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)|(https?://[^\s|]+)")
_SEPARATOR = re.compile(r"[\s|:\-]+")


def build_variables(delivery):
    """Built-in variables derived from the delivery, overridden by custom ones."""
    version = delivery["version"]
    parts = re.split(r"[.\-+]", version)
    created = delivery.get("created_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    values = {
        "version": version,
        "major": parts[0] if len(parts) > 0 else "",
        "minor": parts[1] if len(parts) > 1 else "",
        "patch": parts[2] if len(parts) > 2 else "",
        "date": created[:10],
        "name": delivery.get("name") or "",
    }
    values.update({k: str(v) for k, v in (delivery.get("variables") or {}).items()})
    return values


def render_command(text, variables):
    return _PLACEHOLDER.sub(lambda m: variables.get(m.group(1), m.group(0)), text or "")


def parse_cell(text):
    """Split a cell into (text, url_or_None) segments: [label](url) and bare URLs become links."""
    segments, last = [], 0
    for m in _LINK.finditer(text):
        if m.start() > last:
            segments.append((text[last:m.start()], None))
        if m.group(1):
            segments.append((m.group(1), m.group(2)))
        else:
            segments.append((m.group(3), m.group(3)))
        last = m.end()
    if last < len(text):
        segments.append((text[last:], None))
    return segments


def parse_table(spec, variables):
    """Parse a task table spec: one row per line, cells split by '|', first line is the header.

    Returns {"headers": [cell, ...], "rows": [[cell, ...], ...]} where a cell is a list of
    (text, url) segments, or None when the spec is empty.
    """
    rows = []
    for line in render_command(spec, variables).splitlines():
        line = line.strip()
        if not line or (_SEPARATOR.fullmatch(line) and "-" in line):
            continue
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        rows.append([parse_cell(cell.strip()) for cell in line.split("|")])
    if not rows:
        return None
    width = max(len(r) for r in rows)
    rows = [r + [[] for _ in range(width - len(r))] for r in rows]
    return {"headers": rows[0], "rows": rows[1:]}
