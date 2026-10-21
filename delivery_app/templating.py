"""Variable substitution and link-table parsing (mirrored in static/app.js)."""

import re
from datetime import datetime, timezone

_PLACEHOLDER = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)|(https?://[^\s|]+)")
_SEPARATOR = re.compile(r"[\s|:\-]+")


def build_variables(delivery):
    """Built-in variables derived from the delivery, overridden by custom ones, then resolved."""
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
    return resolve_variables(values)


def resolve_variables(values, limit=10000):
    """Expand {{other}} inside variable values, at any depth and in any order.

    A reference to an unknown or empty variable, or one that loops back (a -> b -> a), is kept as
    written so that it shows up as unresolved.
    """
    def expand(key, stack):
        def sub(m):
            k = m.group(1)
            return m.group(0) if k in stack or not values.get(k) else expand(k, stack | {k})
        return _PLACEHOLDER.sub(sub, values[key])[:limit]
    return {k: expand(k, {k}) for k in values}


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


# -- rich text of notes (mirrored in static/app.js) ---------------------------
#   **gras**  *italique*  __souligné__  ~~barré~~  (\* for a literal star)
#   lines starting with "- " (or "* ", "• ") form a bullet list, "1. " (or "1) ") a numbered list.

_RICH_UL = re.compile(r"^\s*[-*•]\s+(.*)$")
_RICH_OL = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_RICH_TOKEN = re.compile(r"\\([*_~\\])|(\*\*|__|~~|\*)")
RICH_STYLES = {"**": "b", "*": "i", "__": "u", "~~": "s"}


def parse_inline(text):
    """[(text, styles)] where styles is a frozenset of 'b', 'i', 'u', 's'.

    A marker opens a style only when it is followed by a non-space and the same marker closes it
    further on the line, right after a non-space; otherwise it is kept as typed ("rm *.log").
    """
    tokens, last = [], 0
    for m in _RICH_TOKEN.finditer(text):
        if m.start() > last:
            tokens.append((False, text[last:m.start()]))
        tokens.append((False, m.group(1)) if m.group(1) else (True, m.group(2)))
        last = m.end()
    if last < len(text):
        tokens.append((False, text[last:]))
    out, active = [], set()
    for i, (marker, value) in enumerate(tokens):
        if marker:
            style = RICH_STYLES[value]
            if style in active:
                active.discard(style)
                continue
            if _opens(tokens, i):
                active.add(style)
                continue
        styles = frozenset(active)
        if out and out[-1][1] == styles:
            out[-1] = (out[-1][0] + value, styles)
        else:
            out.append((value, styles))
    return out


def _opens(tokens, i):
    """Marker i opens a span: not glued to a word before it ("prev__version"), followed by a
    non-space, and closed later by the same marker preceded by a non-space and not glued to a word after."""
    def text(k):
        return "" if k < 0 or k >= len(tokens) or tokens[k][0] else tokens[k][1]
    if text(i - 1)[-1:].isalnum() or i + 1 >= len(tokens) or text(i + 1)[:1].isspace():
        return False
    for j in range(i + 2, len(tokens)):
        if tokens[j] == tokens[i] and not text(j - 1)[-1:].isspace() and not text(j + 1)[:1].isalnum():
            return True
    return False


def parse_rich(text):
    """Blocks of a note: [{"kind": "p"|"ul"|"ol", "start": n, "items": [[(text, styles)], ...]}].

    A paragraph has a single item (its lines joined by newlines); a blank line separates paragraphs.
    """
    blocks, para = [], []

    def flush():
        if para:
            item = []
            for n, line in enumerate(para):  # styles do not run across lines
                item += ([("\n", frozenset())] if n else []) + parse_inline(line)
            blocks.append({"kind": "p", "start": 1, "items": [item]})
            para.clear()

    in_list = False
    for line in (text or "").split("\n"):
        ul, ol = _RICH_UL.match(line), _RICH_OL.match(line)
        if ul or ol:
            flush()
            kind = "ul" if ul else "ol"
            item = parse_inline(ul.group(1) if ul else ol.group(2))
            if in_list and blocks[-1]["kind"] == kind:
                blocks[-1]["items"].append(item)
            else:
                blocks.append({"kind": kind, "start": int(ol.group(1)) if ol else 1, "items": [item]})
            in_list = True
            continue
        in_list = False
        if line.strip():
            para.append(line)
        else:
            flush()
    flush()
    return blocks
