"""Minimal PDF writer (standard library only).

Flow layout on A4 with the 14 standard fonts (WinAnsi encoding): wrapped rich text,
code blocks, tables with clickable links, PNG/JPEG images and page footers.
"""

import re
import struct
import unicodedata
import zlib

PAGE_W, PAGE_H = 595.28, 841.89
MARGIN = 56.7  # 2 cm

INK = (0.086, 0.125, 0.169)
MUTED = (0.333, 0.376, 0.431)
ACCENT = (0.122, 0.373, 0.478)
LINK = (0.02, 0.388, 0.757)
LINE = (0.784, 0.82, 0.855)
CODE_BG = (0.933, 0.949, 0.961)
ZEBRA = (0.953, 0.965, 0.973)
WHITE = (1, 1, 1)

FONTS = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Helvetica-Oblique", "F4": "Courier",
         "F5": "Helvetica-BoldOblique"}
REGULAR, BOLD, ITALIC, MONO, BOLD_ITALIC = "F1", "F2", "F3", "F4", "F5"

# Advance widths (1/1000 em) for ASCII 32..126, from the standard AFM files.
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556,
         556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778,
         722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278,
         278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
         556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_HELV_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
              556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667,
              611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
              667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556,
              278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]
_SPECIAL = {"—": 1000, "…": 1000, "•": 350, "–": 556, "·": 278, "’": 222, "‘": 222, "“": 333, "”": 333, "«": 556,
            "»": 556, "€": 556, "°": 400, "\u00a0": 278}
_REPLACE = {"\u202f": "\u00a0", "\u2009": " ", "\u2192": "->", "\u2713": "v", "\u2014": "—"}


def clean(text):
    text = "".join(_REPLACE.get(c, c) for c in str(text))
    return text.encode("cp1252", "replace").decode("cp1252")


def char_width(c, font):
    if font == MONO:
        return 600
    table = _HELV_BOLD if font in (BOLD, BOLD_ITALIC) else _HELV
    o = ord(c)
    if 32 <= o <= 126:
        return table[o - 32]
    if c in _SPECIAL:
        return _SPECIAL[c]
    base = unicodedata.normalize("NFD", c)[0]
    if 32 <= ord(base) <= 126:
        return table[ord(base) - 32]
    return 556


def text_width(text, font, size):
    return sum(char_width(c, font) for c in text) * size / 1000


def pdf_string(text):
    raw = clean(text).encode("cp1252", "replace")
    raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").replace(b"\r", b"")
    return "(" + raw.decode("latin-1") + ")"


def rgb(color):
    return " ".join(f"{c:.3f}" for c in color)


class Unsupported(Exception):
    pass


# Decoding a transparent PNG in pure Python takes ~1-4 s for a full-HD screenshot:
# keep recent results so repeated exports are instant. Keys are immutable image ids.
_IMAGE_CACHE = {}


# -- images -----------------------------------------------------------------

def _add_bytes(a, b):
    """Byte-wise (a + b) mod 256 over whole rows at once (SWAR on Python ints)."""
    n = len(a)
    ia, ib = int.from_bytes(a, "big"), int.from_bytes(b, "big")
    low, high = int.from_bytes(b"\x7f" * n, "big"), int.from_bytes(b"\x80" * n, "big")
    return (((ia & low) + (ib & low)) ^ ((ia ^ ib) & high)).to_bytes(n, "big")


def _unfilter(raw, width, height, bpp):
    stride = width * bpp
    out = bytearray()
    prev = bytes(stride)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif ftype == 2:
            row = bytearray(_add_bytes(bytes(row), prev))
        elif ftype == 3:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += row
        prev = bytes(row)
    return bytes(out)


def png_image(data):
    """Return (width, height, image_dict, stream, smask_or_None) for a PNG."""
    pos, idat, palette = 8, [], None
    width = height = depth = ctype = interlace = None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            palette = chunk
        elif kind == b"IDAT":
            idat.append(chunk)
        elif kind == b"IEND":
            break
    if interlace or depth not in (1, 2, 4, 8) or (depth != 8 and ctype != 3):
        raise Unsupported("PNG entrelacé ou 16 bits")
    stream = b"".join(idat)
    if ctype in (0, 2, 3):  # no alpha: hand the PNG predictor stream straight to the PDF
        colors = {0: 1, 2: 3, 3: 1}[ctype]
        if ctype == 3:
            cs = f"[/Indexed /DeviceRGB {len(palette) // 3 - 1} <{palette.hex()}>]"
        else:
            cs = "/DeviceGray" if ctype == 0 else "/DeviceRGB"
        info = (f"/Width {width} /Height {height} /ColorSpace {cs} /BitsPerComponent {depth} /Filter /FlateDecode"
                f" /DecodeParms << /Predictor 15 /Colors {colors} /BitsPerComponent {depth} /Columns {width} >>")
        return width, height, info, stream, None
    if ctype not in (4, 6):
        raise Unsupported("type de PNG inconnu")
    bpp = 2 if ctype == 4 else 4
    pixels = _unfilter(zlib.decompress(stream), width, height, bpp)
    alpha = pixels[bpp - 1::bpp]
    if ctype == 4:
        color, cs = pixels[0::2], "/DeviceGray"
    else:
        buf = bytearray(width * height * 3)
        buf[0::3], buf[1::3], buf[2::3] = pixels[0::4], pixels[1::4], pixels[2::4]
        color, cs = bytes(buf), "/DeviceRGB"
    info = f"/Width {width} /Height {height} /ColorSpace {cs} /BitsPerComponent 8 /Filter /FlateDecode"
    smask = None
    if alpha.count(255) != len(alpha):
        smask = (f"/Width {width} /Height {height} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode",
                 zlib.compress(alpha))
    return width, height, info, zlib.compress(color), smask


def jpeg_image(data):
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            comps = data[i + 9]
            cs = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}.get(comps, "/DeviceRGB")
            extra = " /Decode [1 0 1 0 1 0 1 0]" if comps == 4 else ""
            info = f"/Width {width} /Height {height} /ColorSpace {cs} /BitsPerComponent 8 /Filter /DCTDecode{extra}"
            return width, height, info, data, None
        i += 2 + length
    raise Unsupported("JPEG illisible")


# -- document ---------------------------------------------------------------

class Pdf:
    def __init__(self, title="", footer=""):
        self.title = title
        self.footer = footer
        self.pages = []
        self.images = []
        self.width = PAGE_W - 2 * MARGIN
        self.new_page()

    def new_page(self):
        self.page = {"ops": [], "annots": []}
        self.pages.append(self.page)
        self.y = PAGE_H - MARGIN

    def ensure(self, height):
        if self.y - height < MARGIN + 14 and self.y < PAGE_H - MARGIN - 1:
            self.new_page()

    def space(self, h):
        self.y -= h

    # primitives
    def _text(self, x, y, text, font, size, color):
        self.page["ops"].append(f"BT /{font} {size:.2f} Tf {rgb(color)} rg {x:.2f} {y:.2f} Td {pdf_string(text)} Tj ET")

    def _rect(self, x, y, w, h, fill=None, stroke=None, width=0.5):
        if fill:
            self.page["ops"].append(f"{rgb(fill)} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
        if stroke:
            self.page["ops"].append(f"{rgb(stroke)} RG {width} w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def _link(self, x, y, w, h, url):
        self.page["annots"].append((x, y, x + w, y + h, url))

    # rich text layout: segments are (text, font, color, url[, decorations]) — decorations: "u", "s"
    def layout(self, segments, size, max_width):
        """Wrap segments into lines of (x, word, font, color, url, decorations)."""
        lines, line, x = [], [], 0.0
        for text, font, color, url, *deco in segments:
            deco = deco[0] if deco else ""
            for p, para in enumerate(clean(text).split("\n")):
                if p:
                    lines.append(line)
                    line, x = [], 0.0
                for token in re.findall(r"\S+|\s+", para):
                    if token.isspace():
                        if line:
                            x += text_width(token, font, size)
                        continue
                    w = text_width(token, font, size)
                    if line and x + w > max_width:
                        lines.append(line)
                        line, x = [], 0.0
                    while w > max_width and len(token) > 1:  # hard-break very long words / URLs
                        cut = len(token) - 1
                        while cut > 1 and text_width(token[:cut], font, size) > max_width:
                            cut -= 1
                        lines.append([(0.0, token[:cut], font, color, url, deco)])
                        token = token[cut:]
                        w = text_width(token, font, size)
                    line.append((x, token, font, color, url, deco))
                    x += w
        if line:
            lines.append(line)
        return lines

    def _hline(self, x, y, w, color):
        self.page["ops"].append(f"{rgb(color)} RG 0.4 w {x:.2f} {y:.2f} m {x + w:.2f} {y:.2f} l S")

    def _draw_line(self, line, x0, baseline, size):
        for k, (x, word, font, color, url, deco) in enumerate(line):
            self._text(x0 + x, baseline, word, font, size, color)
            w = text_width(word, font, size)
            # Decorations also cover the space up to the next word of the same span.
            nxt = line[k + 1] if k + 1 < len(line) else None
            span = nxt[0] - x if nxt and nxt[5] == deco and nxt[4] == url else w
            if url or "u" in deco:
                self._hline(x0 + x, baseline - 1.5, span if not url else w, color)
            if "s" in deco:
                self._hline(x0 + x, baseline + size * 0.3, span, color)
            if url:
                self._link(x0 + x, baseline - 2.5, w, size + 2, url)

    def rich(self, segments, size=10, indent=0, after=4, leading=None, marker=None):
        """Wrapped rich text; with marker ("•", "3."), a list item hanging after its marker."""
        leading = leading or size * 1.35
        hang = size * 1.6 if marker else 0
        for n, line in enumerate(self.layout(segments, size, self.width - indent - hang)):
            self.ensure(leading)
            if marker and n == 0:
                self._text(MARGIN + indent, self.y - size, clean(marker), REGULAR, size, line[0][3] if line else INK)
            self._draw_line(line, MARGIN + indent + hang, self.y - size, size)
            self.y -= leading
        self.y -= after

    def text(self, text, font=REGULAR, size=10, color=INK, **kw):
        self.rich([(text, font, color, None)], size=size, **kw)

    def heading(self, text, size=14, color=INK, before=10, after=6):
        self.ensure(before + size * 2.5)
        self.y -= before
        self.text(text, BOLD, size, color, after=after)

    def rule(self, color=LINE):
        self.page["ops"].append(f"{rgb(color)} RG 0.5 w {MARGIN:.2f} {self.y:.2f} m {PAGE_W - MARGIN:.2f} {self.y:.2f} l S")

    def code(self, text, size=8.5):
        leading = size * 1.45
        cols = max(10, int((self.width - 16) / (0.6 * size)))
        lines = []
        for raw in clean(text).split("\n"):
            lines += [raw[i:i + cols] for i in range(0, max(len(raw), 1), cols)]
        self.y -= 2
        for i, line in enumerate(lines):
            pad_top = 5 if i == 0 else 0
            pad_bottom = 5 if i == len(lines) - 1 else 0
            h = leading + pad_top + pad_bottom
            self.ensure(h)
            self._rect(MARGIN, self.y - h, self.width, h, fill=CODE_BG)
            self._text(MARGIN + 8, self.y - pad_top - size, line, MONO, size, INK)
            self.y -= h
        self.y -= 8

    def table(self, rows, widths=None, header=True, size=8.5, zebra=True):
        """rows: list of rows; each cell is a list of (text, font, color, url) segments."""
        if not rows:
            return
        ncols = max(len(r) for r in rows)
        rows = [r + [[] for _ in range(ncols - len(r))] for r in rows]
        pad, leading = 4, size * 1.35
        if not widths:  # share the width by content, with a floor per column
            natural = [max(min(text_width("".join(s[0] for s in cell), BOLD, size), 260) for cell in col) + 2 * pad
                       for col in zip(*rows)]
            natural = [max(n, 40) for n in natural]
            widths = natural
        total = sum(widths)
        widths = [w * self.width / total for w in widths]

        def measure(row, head):
            cells = []
            for cell, w in zip(row, widths):
                segs = [(t, BOLD if head else f, WHITE if head else c, u) for t, f, c, u in cell]
                cells.append(self.layout(segs, size, w - 2 * pad))
            height = max(max(len(c), 1) for c in cells) * leading + 2 * pad
            return cells, height

        def draw(cells, height, head, index):
            x = MARGIN
            for lines, w in zip(cells, widths):
                fill = ACCENT if head else (ZEBRA if zebra and index % 2 == 0 else None)
                self._rect(x, self.y - height, w, height, fill=fill, stroke=LINE)
                y = self.y - pad
                for line in lines:
                    self._draw_line(line, x + pad, y - size, size)
                    y -= leading
                x += w
            self.y -= height

        head = measure(rows[0], True) if header else None
        if head:
            self.ensure(head[1] + 20)
            draw(*head, True, 0)
        for i, row in enumerate(rows[1:] if header else rows):
            cells, height = measure(row, False)
            if self.y - height < MARGIN + 14:
                self.new_page()
                if head:
                    draw(*head, True, 0)
            draw(cells, height, False, i)
        self.y -= 8

    def image(self, data, max_width=None, max_height=300, cache_key=None):
        img = _IMAGE_CACHE.get(cache_key) if cache_key is not None else None
        if img is None:
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                img = png_image(data)
            elif data[:2] == b"\xff\xd8":
                img = jpeg_image(data)
            else:
                raise Unsupported("format non pris en charge")
            if cache_key is not None:
                if len(_IMAGE_CACHE) >= 64:
                    _IMAGE_CACHE.pop(next(iter(_IMAGE_CACHE)))
                _IMAGE_CACHE[cache_key] = img
        width, height = img[0], img[1]
        max_width = max_width or self.width
        scale = min(1.0, max_width / (width * 0.75), max_height / (height * 0.75)) * 0.75
        w, h = width * scale, height * scale
        self.images.append(img)
        self.ensure(h + 4)
        self._rect(MARGIN - 0.5, self.y - h - 0.5, w + 1, h + 1, stroke=LINE)
        self.page["ops"].append(f"q {w:.2f} 0 0 {h:.2f} {MARGIN:.2f} {self.y - h:.2f} cm /Im{len(self.images)} Do Q")
        self.y -= h + 4

    # serialisation
    def to_bytes(self):
        objects = {}

        def obj(n, body):
            objects[n] = body if isinstance(body, bytes) else body.encode("latin-1")

        def stream(dict_body, data):
            return f"<< {dict_body} /Length {len(data)} >>\nstream\n".encode("latin-1") + data + b"\nendstream"

        font_ids = {name: 3 + i for i, name in enumerate(FONTS)}
        for name, base in FONTS.items():
            obj(font_ids[name], f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>")
        next_id = 3 + len(FONTS)
        image_ids = []
        for _, _, info, data, smask in self.images:
            smask_ref = ""
            if smask:
                obj(next_id, stream("/Type /XObject /Subtype /Image " + smask[0], smask[1]))
                smask_ref = f" /SMask {next_id} 0 R"
                next_id += 1
            obj(next_id, stream("/Type /XObject /Subtype /Image " + info + smask_ref, data))
            image_ids.append(next_id)
            next_id += 1
        fonts = " ".join(f"/{n} {i} 0 R" for n, i in font_ids.items())
        xobjects = " ".join(f"/Im{i + 1} {oid} 0 R" for i, oid in enumerate(image_ids))
        resources = f"<< /Font << {fonts} >>" + (f" /XObject << {xobjects} >>" if xobjects else "") + " >>"

        page_ids = []
        total = len(self.pages)
        for number, page in enumerate(self.pages, 1):
            ops = list(page["ops"])
            if self.footer:
                label = f"{self.footer} · page {number}/{total}"
                ops.append(f"{rgb(LINE)} RG 0.5 w {MARGIN:.2f} {MARGIN - 8:.2f} m {PAGE_W - MARGIN:.2f} {MARGIN - 8:.2f} l S")
                ops.append(f"BT /F1 7.5 Tf {rgb(MUTED)} rg {MARGIN:.2f} {MARGIN - 20:.2f} Td {pdf_string(label)} Tj ET")
            content = zlib.compress("\n".join(ops).encode("latin-1"))
            content_id, page_id = next_id, next_id + 1
            next_id += 2
            obj(content_id, stream("/Filter /FlateDecode", content))
            annots = []
            for x1, y1, x2, y2, url in page["annots"]:
                obj(next_id, f"<< /Type /Annot /Subtype /Link /Rect [{x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f}] "
                             f"/Border [0 0 0] /A << /S /URI /URI {pdf_string(url)} >> >>")
                annots.append(f"{next_id} 0 R")
                next_id += 1
            obj(page_id, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources {resources} "
                         f"/Contents {content_id} 0 R" + (f" /Annots [{' '.join(annots)}]" if annots else "") + " >>")
            page_ids.append(page_id)
        obj(1, "<< /Type /Catalog /Pages 2 0 R >>")
        obj(2, f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>")
        info_id = next_id
        obj(info_id, f"<< /Title {pdf_string(self.title)} /Producer (Checklist Livraison) >>")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for n in sorted(objects):
            offsets[n] = len(out)
            out += f"{n} 0 obj\n".encode() + objects[n] + b"\nendobj\n"
        xref = len(out)
        size = max(objects) + 1
        out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
        for n in range(1, size):
            out += (f"{offsets[n]:010d} 00000 n \n" if n in offsets else "0000000000 65535 f \n").encode()
        out += f"trailer\n<< /Size {size} /Root 1 0 R /Info {info_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)
