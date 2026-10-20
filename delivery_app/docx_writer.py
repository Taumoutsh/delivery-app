"""Minimal .docx writer (standard library only): paragraphs, headings, code,
tables with hyperlinks and inline PNG/JPEG/GIF images."""

import io
import re
import struct
import zipfile
from xml.sax.saxutils import escape

ACCENT = "1F5F7A"
MUTED = "55606E"
BORDER = "C8D1DA"
PAGE_WIDTH_TWIPS = 11906 - 2 * 1134  # A4 minus 2 cm margins
EMU_PER_PX = 9525  # 96 dpi
EMU_PER_CM = 360000

_INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
REL_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


def x(text):
    return escape(_INVALID_XML.sub("", str(text)), {'"': "&quot;"})


def image_size(data):
    """(width, height) in pixels for PNG, JPEG or GIF data, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    if data[:2] == b"\xff\xd8":
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
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + length
    return None


def image_ext(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


class Docx:
    def __init__(self, title=""):
        self.title = title
        self.body = []
        self.rels = []
        self.media = []

    # -- inline content -------------------------------------------------

    def _rel(self, kind, target, external=False):
        rid = f"rId{len(self.rels) + 10}"
        self.rels.append((rid, kind, target, external))
        return rid

    def run(self, text, bold=False, italic=False, mono=False, color=None, size=None, style=None):
        props = ""
        if style:
            props += f'<w:rStyle w:val="{style}"/>'
        if mono:
            props += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
        if bold:
            props += "<w:b/>"
        if italic:
            props += "<w:i/>"
        if color:
            props += f'<w:color w:val="{color}"/>'
        if size:
            props += f'<w:sz w:val="{int(size * 2)}"/><w:szCs w:val="{int(size * 2)}"/>'
        lines = str(text).split("\n")
        content = "<w:br/>".join(f'<w:t xml:space="preserve">{x(line)}</w:t>' for line in lines)
        return f"<w:r>{f'<w:rPr>{props}</w:rPr>' if props else ''}{content}</w:r>"

    def link(self, text, url, **kw):
        rid = self._rel(REL_HYPERLINK, url, external=True)
        return f'<w:hyperlink r:id="{rid}" w:history="1">{self.run(text, style="Hyperlink", **kw)}</w:hyperlink>'

    def segments(self, segments, **kw):
        """Runs for [(text, url_or_None), ...] as produced by templating.parse_cell."""
        return "".join(self.link(t, u, **kw) if u else self.run(t, **kw) for t, u in segments)

    # -- blocks ---------------------------------------------------------

    def paragraph(self, runs, style=None, keep_next=False, after=None):
        props = ""
        if style:
            props += f'<w:pStyle w:val="{style}"/>'
        if keep_next:
            props += "<w:keepNext/>"
        if after is not None:
            props += f'<w:spacing w:after="{after}"/>'
        if isinstance(runs, str) and not runs.startswith("<w:"):
            runs = self.run(runs)
        self.body.append(f"<w:p>{f'<w:pPr>{props}</w:pPr>' if props else ''}{''.join(runs)}</w:p>")

    def heading(self, text, level=1):
        self.paragraph(self.run(text), style="Title" if level == 0 else f"Heading{level}", keep_next=True)

    def code(self, text):
        self.paragraph(self.run(text, mono=True), style="Code")

    def table(self, rows, header=True, widths=None):
        """rows: list of rows, each a list of run-XML strings (one per cell)."""
        if not rows:
            return
        ncols = max(len(r) for r in rows)
        widths = widths or [1] * ncols
        total = sum(widths)
        cols = [int(PAGE_WIDTH_TWIPS * w / total) for w in widths]
        borders = "".join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="{BORDER}"/>'
                          for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
        out = [
            '<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>'
            f"<w:tblBorders>{borders}</w:tblBorders>"
            '<w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
            '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0"'
            ' w:noHBand="0" w:noVBand="1"/></w:tblPr>',
            "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{c}"/>' for c in cols) + "</w:tblGrid>",
        ]
        for i, row in enumerate(rows):
            is_head = header and i == 0
            out.append("<w:tr>" + ("<w:trPr><w:tblHeader/></w:trPr>" if is_head else '<w:trPr><w:cantSplit/></w:trPr>'))
            for j in range(ncols):
                runs = row[j] if j < len(row) else ""
                shade = f'<w:shd w:val="clear" w:color="auto" w:fill="{ACCENT}"/>' if is_head else ""
                out.append(f'<w:tc><w:tcPr><w:tcW w:w="{cols[j]}" w:type="dxa"/>{shade}</w:tcPr>'
                           f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr>{runs}</w:p></w:tc>')
            out.append("</w:tr>")
        out.append("</w:tbl>")
        self.body.append("".join(out))
        self.paragraph("", after=0)

    def image(self, data, filename, max_width_cm=16, max_height_cm=12):
        ext, size = image_ext(data), image_size(data)
        if not ext or not size:
            return False
        name = f"image{len(self.media) + 1}.{ext}"
        self.media.append((name, data))
        rid = self._rel(REL_IMAGE, f"media/{name}")
        cx, cy = size[0] * EMU_PER_PX, size[1] * EMU_PER_PX
        ratio = min(1.0, max_width_cm * EMU_PER_CM / cx, max_height_cm * EMU_PER_CM / cy)
        cx, cy = int(cx * ratio), int(cy * ratio)
        n = len(self.media)
        drawing = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{n}" name="{x(filename)}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/>'
            '</wp:cNvGraphicFramePr><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{n}" name="{x(filename)}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            "</wp:inline></w:drawing></w:r>")
        self.paragraph(drawing, keep_next=True, after=40)
        return True

    # -- package --------------------------------------------------------

    def to_bytes(self):
        document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>'
                    + "".join(self.body)
                    + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134"'
                      ' w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
                      "</w:body></w:document>")
        rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/styles" Target="styles.xml"/>']
        for rid, kind, target, external in self.rels:
            mode = ' TargetMode="External"' if external else ""
            rels.append(f'<Relationship Id="{rid}" Type="{kind}" Target="{x(target)}"{mode}/>')
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("docProps/core.xml", CORE.format(title=x(self.title)))
            z.writestr("word/document.xml", document)
            z.writestr("word/styles.xml", STYLES)
            z.writestr("word/_rels/document.xml.rels",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns='
                       '"http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(rels)
                       + "</Relationships>")
            for name, data in self.media:
                z.writestr(f"word/media/{name}", data)
        return out.getvalue()


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="jpeg" ContentType="image/jpeg"/>
<Default Extension="gif" ContentType="image/gif"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title><dc:creator>Checklist Livraison</dc:creator></cp:coreProperties>"""

STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults>
 <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault>
 <w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
 <w:pPr><w:spacing w:after="200"/></w:pPr><w:rPr><w:b/><w:color w:val="16202B"/><w:sz w:val="44"/><w:szCs w:val="44"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
 <w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="{ACCENT}"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
 <w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="16202B"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
 <w:pPr><w:keepNext/><w:spacing w:before="160" w:after="60"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:color w:val="{MUTED}"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:qFormat/>
 <w:pPr><w:shd w:val="clear" w:color="auto" w:fill="EEF2F5"/><w:spacing w:before="60" w:after="120" w:line="240" w:lineRule="auto"/><w:ind w:left="113" w:right="113"/></w:pPr>
 <w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>
</w:styles>"""
