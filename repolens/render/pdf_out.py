"""PDF renderer (ReportLab).

Layout: a cover page with the project name and release metadata, a table of contents, and
the body with numbered h1 sections. Fonts with Unicode coverage are used when the system
has them (Arial Unicode / DejaVu); otherwise the built-in fonts are used and characters
they cannot draw are replaced by ASCII look-alikes.
"""

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
HEADING = colors.HexColor("#2A2238")
MARGIN = 2 * cm

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


def _register_fonts() -> None:
    """Register the first available font for each role (once per process)."""
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
    """ReportLab paragraph markup for text with inline `code`, **bold**, and *italic*."""
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
    """A document that records h1/h2 headings for the table of contents."""

    def __init__(self, *args, title_text="", **kwargs):
        super().__init__(*args, **kwargs)
        self.title_text = title_text

    def afterFlowable(self, flowable):
        level = getattr(flowable, "_toc_level", None)
        if level is not None:
            self.notify("TOCEntry", (level, flowable.getPlainText(), self.page))


def render(blocks: list[dict], path: Path) -> Path:
    """Write the blocks to a PDF at `path`: a cover page, a table of contents, then the body."""
    _register_fonts()
    story = _Story()
    for block in blocks:
        story.add(block)
    doc = _Doc(
        str(path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"{story.title_text} - " + tr("Technical Documentation", "Dokumentasi Teknis"),
        author="repolens",
        title_text=story.title_text,
    )
    doc.multiBuild(story.flowables, onFirstPage=_page_frame, onLaterPages=_page_frame)
    return path


def _page_frame(canvas, doc) -> None:
    """Running header (title) and page number on every page except the cover."""
    if doc.page == 1:
        return
    regular = _FONTS["regular"]
    canvas.saveState()
    canvas.setFont(regular, 7.5)
    canvas.setFillColor(MUTED)
    header = f"{doc.title_text} · " + tr("Technical Documentation", "Dokumentasi Teknis")
    canvas.drawString(MARGIN, A4[1] - 1.2 * cm, _fit(header, regular))
    canvas.drawRightString(A4[0] - MARGIN, 1.2 * cm, tr("Page ", "Halaman ") + str(doc.page))
    canvas.setStrokeColor(RULE)
    canvas.line(MARGIN, A4[1] - 1.35 * cm, A4[0] - MARGIN, A4[1] - 1.35 * cm)
    canvas.restoreState()


class _Story:
    """Turns blocks into ReportLab flowables; one `_<type>` method per block type."""

    def __init__(self):
        self.styles = _styles()
        self.flowables: list = []
        self.title_text = ""
        self.h1_count = 0  # h1 headings are numbered: "1. Summary"
        self.width = A4[0] - 2 * MARGIN

    def add(self, block: dict) -> None:
        handler = getattr(self, "_" + block["t"], None)
        if handler:
            handler(block)

    def _title(self, block: dict) -> None:
        """Cover page (subtitle, title, metadata table), then the table of contents."""
        s = self.styles
        self.title_text = block["title"]
        meta = [
            [Paragraph(_markup(key), s["meta_key"]), Paragraph(_markup(value), s["meta_value"])]
            for key, value in block["meta"]
        ]
        meta_table = Table(meta, colWidths=[4 * cm, self.width - 4 * cm])
        meta_table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        toc = TableOfContents()
        toc.levelStyles = [s["toc1"], s["toc2"]]
        self.flowables += [
            Spacer(1, 6 * cm),
            Paragraph(_markup(block["subtitle"].upper()), s["subtitle"]),
            Paragraph(_markup(block["title"], "bold"), s["title"]),
            meta_table,
            PageBreak(),
            Paragraph(tr("Contents", "Daftar Isi"), s["h1"]),
            toc,
            PageBreak(),
        ]

    def _h1(self, block: dict) -> None:
        self.h1_count += 1
        heading = Paragraph(_markup(f"{self.h1_count}. {block['text']}", "bold"), self.styles["h1"])
        heading._toc_level = 0
        self.flowables += [CondPageBreak(5 * cm), heading]

    def _h2(self, block: dict) -> None:
        heading = Paragraph(_markup(block["text"], "bold"), self.styles["h2"])
        heading._toc_level = 1
        self.flowables += [CondPageBreak(4 * cm), heading]

    def _h3(self, block: dict) -> None:
        heading = Paragraph(_markup(block["text"], "bold"), self.styles["h3"])
        self.flowables += [CondPageBreak(3 * cm), heading]

    def _p(self, block: dict) -> None:
        self.flowables.append(Paragraph(_markup(block["text"]), self.styles["body"]))

    def _bullets(self, block: dict) -> None:
        for item in block["items"]:
            self.flowables.append(Paragraph(_markup(item), self.styles["bullet"], bulletText="•"))
        self.flowables.append(Spacer(1, 4))

    def _note(self, block: dict) -> None:
        warn = block.get("level") == "warn"
        label = tr("Warning: ", "Perhatian: ") if warn else tr("Note: ", "Catatan: ")
        style = self.styles["note_warn" if warn else "note_info"]
        text = f'<font face="{_FONTS["bold"]}">{label}</font>' + _markup(block["text"])
        self.flowables.append(Paragraph(text, style))

    def _code(self, block: dict) -> None:
        self.flowables.append(
            Preformatted(_fit(block["text"], _FONTS["mono"]), self.styles["code"])
        )

    def _table(self, block: dict) -> None:
        """Header row in the brand colour, zebra rows; short tables are kept on one page."""
        s = self.styles
        headers, rows = block["headers"], block["rows"]
        weights = block.get("widths") or [1] * len(headers)
        widths = [self.width * w / sum(weights) for w in weights]
        data = [[Paragraph(_markup(h, "bold"), s["cell_head"]) for h in headers]]
        data += [[Paragraph(_markup(cell), s["small"]) for cell in row] for row in rows]
        table = Table(data, colWidths=widths, repeatRows=1)
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
        style += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]
        table.setStyle(TableStyle(style))
        self.flowables += [KeepTogether([table]) if len(rows) <= 6 else table, Spacer(1, 10)]

    def _pagebreak(self, block: dict) -> None:
        self.flowables.append(PageBreak())


def _styles() -> dict[str, ParagraphStyle]:
    """Every paragraph style of the document, built after the fonts are registered."""
    regular, bold, mono = _FONTS["regular"], _FONTS["bold"], _FONTS["mono"]
    body = ParagraphStyle(
        "body", fontName=regular, fontSize=9.5, leading=13.5, spaceAfter=6, alignment=TA_LEFT
    )
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, spaceAfter=0)
    note = ParagraphStyle("note", parent=body, borderPadding=7, spaceBefore=4, spaceAfter=10)
    return {
        "body": body,
        "small": small,
        "cell_head": ParagraphStyle(
            "cellhead", parent=small, fontName=bold, textColor=colors.white
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName=bold,
            fontSize=16,
            leading=20,
            textColor=BRAND,
            spaceBefore=6,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=bold,
            fontSize=12.5,
            leading=16,
            textColor=BRAND,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3",
            fontName=bold,
            fontSize=10.5,
            leading=14,
            textColor=HEADING,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "code": ParagraphStyle(
            "code",
            fontName=mono,
            fontSize=7.2,
            leading=9.2,
            backColor=CODE_BG,
            borderPadding=6,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "note_info": ParagraphStyle("n", parent=note, backColor=NOTE_INFO),
        "note_warn": ParagraphStyle("n", parent=note, backColor=NOTE_WARN),
        "bullet": ParagraphStyle(
            "bullet", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=3
        ),
        "subtitle": ParagraphStyle("sub", parent=body, fontName=bold, textColor=MUTED, fontSize=10),
        "title": ParagraphStyle(
            "title", fontName=bold, fontSize=28, leading=34, textColor=BRAND, spaceAfter=18
        ),
        "meta_key": ParagraphStyle("mk", parent=small, textColor=MUTED, fontSize=9, leading=12),
        "meta_value": ParagraphStyle("mv", parent=small, fontSize=9, leading=12),
        "toc1": ParagraphStyle("toc1", parent=body, fontSize=10, leftIndent=0, spaceAfter=3),
        "toc2": ParagraphStyle(
            "toc2", parent=body, fontSize=8.8, leftIndent=14, textColor=MUTED, spaceAfter=1
        ),
    }
