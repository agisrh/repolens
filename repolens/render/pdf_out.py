"""PDF renderer (ReportLab)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from repolens.i18n import t as tr  # `t` is the block type in render()
from repolens.render.inline import segments

BRAND = colors.HexColor("#4D148C")
MUTED = colors.HexColor("#625C6E")
RULE = colors.HexColor("#E2DEE9")
ZEBRA = colors.HexColor("#F6F5F9")
CODE_BG = colors.HexColor("#F1EFF5")
NOTE_INFO = colors.HexColor("#EFE8F8")
NOTE_WARN = colors.HexColor("#FDF0E7")

FONT_CANDIDATES = {
    "regular": [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "italic": [
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "C:/Windows/Fonts/ariali.ttf",
    ],
    "mono": [
        ("/System/Library/Fonts/Menlo.ttc", 0),
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ],
}
BUILTIN = {
    "regular": "Helvetica",
    "bold": "Helvetica-Bold",
    "italic": "Helvetica-Oblique",
    "mono": "Courier",
}
ASCII_FALLBACK = {
    "→": "->",
    "←": "<-",
    "✓": "v",
    "—": "-",
    "–": "-",
    "…": "...",
    "├": "|",
    "└": "`",
    "│": "|",
    "─": "-",
    "·": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "≤": "<=",
    "≥": ">=",
}

_FONTS: dict[str, str] = {}
_CMAPS: dict[str, set[int] | None] = {}


def _register_fonts():
    if _FONTS:
        return
    for role, candidates in FONT_CANDIDATES.items():
        for cand in candidates:
            path, index = cand if isinstance(cand, tuple) else (cand, 0)
            if not Path(path).exists():
                continue
            name = f"Doc-{role}"
            try:
                font = TTFont(name, path, subfontIndex=index)
                pdfmetrics.registerFont(font)
            except Exception:
                continue
            _FONTS[role] = name
            _CMAPS[name] = set(font.face.charToGlyph.keys())
            break
        else:
            _FONTS[role] = BUILTIN[role]
            _CMAPS[BUILTIN[role]] = None


def _fit(text: str, font: str) -> str:
    """Replace characters the font cannot draw."""
    cmap = _CMAPS.get(font)
    if cmap is None:
        text = "".join(ASCII_FALLBACK.get(c, c) for c in text)
        return text.encode("latin-1", "replace").decode("latin-1")
    return "".join(c if ord(c) in cmap or c in "\n\t" else ASCII_FALLBACK.get(c, "?") for c in text)


def _markup(text: str, base: str = "regular") -> str:
    out = []
    for content, style in segments(str(text)):
        if style == "code":
            f = _FONTS["mono"]
            out.append(f'<font face="{f}" color="#3B2A5C">{escape(_fit(content, f))}</font>')
        elif style == "bold":
            f = _FONTS["bold"]
            out.append(f'<font face="{f}">{escape(_fit(content, f))}</font>')
        elif style == "italic":
            f = _FONTS["italic"]
            out.append(f'<font face="{f}">{escape(_fit(content, f))}</font>')
        else:
            out.append(escape(_fit(content, _FONTS[base])))
    return "".join(out)


class _Doc(SimpleDocTemplate):
    def __init__(self, *args, title_text="", **kwargs):
        super().__init__(*args, **kwargs)
        self.title_text = title_text

    def afterFlowable(self, flowable):
        level = getattr(flowable, "_toc_level", None)
        if level is not None:
            self.notify("TOCEntry", (level, flowable.getPlainText(), self.page))


def render(blocks: list[dict], path: Path) -> Path:
    _register_fonts()
    reg, bold, mono = _FONTS["regular"], _FONTS["bold"], _FONTS["mono"]
    body = ParagraphStyle(
        "body", fontName=reg, fontSize=9.5, leading=13.5, spaceAfter=6, alignment=TA_LEFT
    )
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, spaceAfter=0)
    cell_head = ParagraphStyle("cellhead", parent=small, fontName=bold, textColor=colors.white)
    h1 = ParagraphStyle(
        "h1", fontName=bold, fontSize=16, leading=20, textColor=BRAND, spaceBefore=6, spaceAfter=10
    )
    h2 = ParagraphStyle(
        "h2",
        fontName=bold,
        fontSize=12.5,
        leading=16,
        textColor=BRAND,
        spaceBefore=10,
        spaceAfter=6,
    )
    h3 = ParagraphStyle(
        "h3",
        fontName=bold,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#2A2238"),
        spaceBefore=8,
        spaceAfter=4,
    )
    code = ParagraphStyle(
        "code",
        fontName=mono,
        fontSize=7.2,
        leading=9.2,
        backColor=CODE_BG,
        borderPadding=6,
        spaceBefore=4,
        spaceAfter=10,
    )
    note = ParagraphStyle("note", parent=body, borderPadding=7, spaceBefore=4, spaceAfter=10)
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=3)

    width = A4[0] - 4 * cm
    story = []
    title_text = ""
    h1_index = 0
    for blk in blocks:
        t = blk["t"]
        if t == "title":
            title_text = blk["title"]
            story.append(Spacer(1, 6 * cm))
            story.append(
                Paragraph(
                    _markup(blk["subtitle"].upper()),
                    ParagraphStyle("sub", parent=body, fontName=bold, textColor=MUTED, fontSize=10),
                )
            )
            story.append(
                Paragraph(
                    _markup(blk["title"], "bold"),
                    ParagraphStyle(
                        "title",
                        fontName=bold,
                        fontSize=28,
                        leading=34,
                        textColor=BRAND,
                        spaceAfter=18,
                    ),
                )
            )
            meta = [
                [
                    Paragraph(
                        _markup(k),
                        ParagraphStyle("mk", parent=small, textColor=MUTED, fontSize=9, leading=12),
                    ),
                    Paragraph(
                        _markup(v), ParagraphStyle("mv", parent=small, fontSize=9, leading=12)
                    ),
                ]
                for k, v in blk["meta"]
            ]
            mt = Table(meta, colWidths=[4 * cm, width - 4 * cm])
            mt.setStyle(
                TableStyle(
                    [
                        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story += [mt, PageBreak()]
            story.append(Paragraph(tr("Contents", "Daftar Isi"), h1))
            toc = TableOfContents()
            toc.levelStyles = [
                ParagraphStyle("toc1", parent=body, fontSize=10, leftIndent=0, spaceAfter=3),
                ParagraphStyle(
                    "toc2", parent=body, fontSize=8.8, leftIndent=14, textColor=MUTED, spaceAfter=1
                ),
            ]
            story += [toc, PageBreak()]
        elif t == "h1":
            story.append(CondPageBreak(5 * cm))
            h1_index += 1
            para = Paragraph(_markup(f"{h1_index}. {blk['text']}", "bold"), h1)
            para._toc_level = 0
            story.append(para)
        elif t == "h2":
            story.append(CondPageBreak(4 * cm))
            para = Paragraph(_markup(blk["text"], "bold"), h2)
            para._toc_level = 1
            story.append(para)
        elif t == "h3":
            story.append(CondPageBreak(3 * cm))
            story.append(Paragraph(_markup(blk["text"], "bold"), h3))
        elif t == "p":
            story.append(Paragraph(_markup(blk["text"]), body))
        elif t == "bullets":
            for item in blk["items"]:
                story.append(Paragraph(_markup(item), bullet, bulletText="•"))
            story.append(Spacer(1, 4))
        elif t == "note":
            warn = blk.get("level") == "warn"
            label = tr("Warning: ", "Perhatian: ") if warn else tr("Note: ", "Catatan: ")
            style = ParagraphStyle("n", parent=note, backColor=NOTE_WARN if warn else NOTE_INFO)
            story.append(
                Paragraph(f'<font face="{bold}">{label}</font>' + _markup(blk["text"]), style)
            )
        elif t == "code":
            story.append(Preformatted(_fit(blk["text"], mono), code))
        elif t == "table":
            headers, rows = blk["headers"], blk["rows"]
            widths = blk.get("widths") or [1] * len(headers)
            total = sum(widths)
            col_widths = [width * w / total for w in widths]
            data = [[Paragraph(_markup(h, "bold"), cell_head) for h in headers]]
            data += [[Paragraph(_markup(c), small) for c in row] for row in rows]
            table = Table(data, colWidths=col_widths, repeatRows=1)
            style = [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
                ("BOX", (0, 0), (-1, -1), 0.4, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
            for i in range(2, len(data), 2):
                style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
            table.setStyle(TableStyle(style))
            story.append(KeepTogether([table]) if len(rows) <= 6 else table)
            story.append(Spacer(1, 10))
        elif t == "pagebreak":
            story.append(PageBreak())

    def on_page(canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setFont(reg, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            2 * cm,
            A4[1] - 1.2 * cm,
            _fit(f"{doc.title_text} · " + tr("Technical Documentation", "Dokumentasi Teknis"), reg),
        )
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, tr("Page ", "Halaman ") + str(doc.page))
        canvas.setStrokeColor(RULE)
        canvas.line(2 * cm, A4[1] - 1.35 * cm, A4[0] - 2 * cm, A4[1] - 1.35 * cm)
        canvas.restoreState()

    doc = _Doc(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"{title_text} - " + tr("Technical Documentation", "Dokumentasi Teknis"),
        author="repolens",
        title_text=title_text,
    )
    doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
    return path
