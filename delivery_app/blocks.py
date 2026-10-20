"""Task content blocks: server-side registry (mirror of static/blocks.js).

A task holds an ordered list of blocks {"id": str, "type": str, ...fields}. Each type lists its
text fields and the field that must be filled for the block to be kept. Adding a type means:
an entry here, one in static/blocks.js, and its rendering in report.py (BLOCK_RENDERERS).
"""

import re
import secrets

# type -> (text fields, required field). "media" also carries a "files" list.
TYPES = {
    "command": (("label", "text"), "text"),
    "link": (("label", "url"), "url"),
    "program": (("name", "path", "args", "cwd"), "path"),
    "table": (("title", "spec"), "spec"),
    "media": (("title",), "files"),
    "note": (("text",), "text"),
}
# Fields kept verbatim (multi-line content); the others are stripped.
_RAW = {"text", "spec"}
_ID = re.compile(r"^[\w-]{1,40}$")


def new_id():
    return "b" + secrets.token_hex(5)


def _clean_files(files):
    out = []
    for f in files if isinstance(files, list) else []:
        try:
            media_id = int(f.get("id")) if isinstance(f, dict) else int(f)
        except (TypeError, ValueError):
            continue
        out.append(media_id)
    return out


def normalize(blocks):
    """Validated list of blocks: known types only, string fields, empty blocks dropped.

    Media files are stored as a list of media ids (see Database.media_info for their details).
    """
    out = []
    for raw in blocks if isinstance(blocks, list) else []:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("type")
        if kind not in TYPES:
            raise ValueError(f"Type d'élément inconnu : {kind}")
        fields, required = TYPES[kind]
        block = {"id": raw["id"] if isinstance(raw.get("id"), str) and _ID.match(raw["id"]) else new_id(),
                 "type": kind}
        for name in fields:
            value = str(raw.get(name) or "")
            block[name] = value if name in _RAW else value.strip()
        if kind == "media":
            block["files"] = _clean_files(raw.get("files"))
        if (block["files"] if kind == "media" else block[required].strip()):
            out.append(block)
    return out


def texts(block):
    """Strings of a block that may contain {{variables}}."""
    return [block.get(name, "") for name in TYPES.get(block["type"], ((), None))[0]]


def media_ids(blocks):
    return [media_id for b in blocks if b["type"] == "media" for media_id in b["files"]]
