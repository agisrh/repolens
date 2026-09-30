"""Word (.docx) renderer."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from repolens.render.inline import segments
from repolens.i18n import t as tr  # `t` is the block type in render()

BRAND = RGBColor(0x4D, 0x14, 0x8C)
MUTED = RGBColor(0x62, 0x5C, 0x6E)
MONO = "Consolas"


def _shade(cell_or_par, hex_fill: str):
    el = cell_or_par._tc if hasattr(cell_or_par, "_tc") else cell_or_par._p
    props = el.get_or_add_tcPr() if hasattr(cell_or_par, "_tc") else el.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    props.append(shd)


def _add_runs(par, text: str, size: float | None = None, color: RGBColor | None = None, bold: bool = False):
    for content, style in segments(text):
        run = par.add_run(content)
        if style == "code":
            run.font.name = MONO
            run.font.size = Pt((size or 10.5) - 1)
        elif style == "bold":
            run.bold = True
        elif style == "italic":
            run.italic = True
        if bold:
            run.bold = True
        if size and style != "code":
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = color


def _field(par, instruction: str):
    run = par.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def _repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def render(blocks: list[dict], path: Path) -> Path:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin"):
        setattr(section, side, Cm(2))
    section.top_margin = section.bottom_margin = Cm(2)
    usable = 17.0

    styles = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(10.5)
    for name, size in (("Heading 1", 17), ("Heading 2", 13.5), ("Heading 3", 11.5)):
        styles[name].font.color.rgb = BRAND
        styles[name].font.size = Pt(size)

    title_text = ""
    h1 = 0
    for blk in blocks:
        t = blk["t"]
        if t == "title":
            title_text = blk["title"]
            for _ in range(6):
                doc.add_paragraph()
            par = doc.add_paragraph()
            _add_runs(par, blk["subtitle"].upper(), size=11, color=MUTED, bold=True)
            par = doc.add_paragraph()
            _add_runs(par, blk["title"], size=30, color=BRAND, bold=True)
            doc.add_paragraph()
            table = doc.add_table(rows=0, cols=2)
            for k, v in blk["meta"]:
                cells = table.add_row().cells
                cells[0].width, cells[1].width = Cm(4.5), Cm(12.5)
                _add_runs(cells[0].paragraphs[0], k, size=10, color=MUTED)
                _add_runs(cells[1].paragraphs[0], v, size=10)
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            doc.add_heading(tr("Contents", "Daftar Isi"), level=1)
            toc = doc.add_paragraph()
            _field(toc, 'TOC \\o "1-2" \\h \\z \\u')
            hint = doc.add_paragraph()
            _add_runs(hint, tr("Right-click and choose *Update Field* to refresh the table of contents.", "Klik kanan lalu pilih *Update Field* untuk memperbarui daftar isi."), size=9, color=MUTED)
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif t == "h1":
            h1 += 1
            doc.add_heading(f"{h1}. {blk['text']}", level=1)
        elif t == "h2":
            doc.add_heading(blk["text"], level=2)
        elif t == "h3":
            doc.add_heading(blk["text"], level=3)
        elif t == "p":
            _add_runs(doc.add_paragraph(), blk["text"])
        elif t == "bullets":
            for item in blk["items"]:
                _add_runs(doc.add_paragraph(style="List Bullet"), item)
        elif t == "note":
            par = doc.add_paragraph()
            _shade(par, "FDF0E7" if blk.get("level") == "warn" else "EFE8F8")
            label = tr("Warning: ", "Perhatian: ") if blk.get("level") == "warn" else tr("Note: ", "Catatan: ")
            run = par.add_run(label)
            run.bold = True
            _add_runs(par, blk["text"])
        elif t == "code":
            par = doc.add_paragraph()
            _shade(par, "F1EFF5")
            par.paragraph_format.space_after = Pt(8)
            lines = blk["text"].split("\n")
            for i, line in enumerate(lines):
                run = par.add_run(line)
                run.font.name = MONO
                run._element.rPr.rFonts.set(qn("w:eastAsia"), MONO)
                run.font.size = Pt(8)
                if i < len(lines) - 1:
                    run.add_break()
        elif t == "table":
            headers, rows = blk["headers"], blk["rows"]
            widths = blk.get("widths") or [1] * len(headers)
            total = sum(widths)
            table = doc.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.LEFT
            font_size = 8.5 if len(headers) >= 4 else 9.5
            hdr = table.rows[0]
            _repeat_header(hdr)
            for i, h in enumerate(headers):
                cell = hdr.cells[i]
                _shade(cell, "4D148C")
                _add_runs(cell.paragraphs[0], h, size=font_size, color=RGBColor(0xFF, 0xFF, 0xFF), bold=True)
            for r_i, row in enumerate(rows):
                cells = table.add_row().cells
                for i, value in enumerate(row):
                    _add_runs(cells[i].paragraphs[0], str(value), size=font_size)
                    if r_i % 2:
                        _shade(cells[i], "F6F5F9")
            for row in table.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(usable * w / total)
            doc.add_paragraph()

    header = section.header.paragraphs[0]
    _add_runs(header, f"{title_text} · " + tr("Technical Documentation", "Dokumentasi Teknis"), size=8, color=MUTED)
    footer = section.footer.paragraphs[0]
    _add_runs(footer, tr("Page ", "Halaman "), size=8, color=MUTED)
    _field(footer, "PAGE")
    doc.save(path)
    return path
