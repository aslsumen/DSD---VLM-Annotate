"""Convert the project's Markdown documents to a styled DOCX.

Supports the subset used by docs/: ATX headings, paragraphs, bullet/numbered lists,
pipe tables, blockquotes, fenced code, horizontal rules and inline bold/italic/code/links.

Usage:
    <python-with-python-docx> scripts/md_to_docx.py <input.md> <output.docx> [title]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ACCENT = RGBColor(0x1D, 0x4E, 0xD8)
INK = RGBColor(0x11, 0x18, 0x27)
MUTED = RGBColor(0x6B, 0x72, 0x80)

INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*\n]+?\*)")


def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr)
    run._r.append(fld_char2)


def _inline_runs(paragraph, text: str) -> None:
    position = 0
    for match in INLINE.finditer(text):
        if match.start() > position:
            paragraph.add_run(text[position : match.start()])
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            paragraph.add_run(token[2:-2]).bold = True
        elif token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
        elif token.startswith("["):
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()  # type: ignore[union-attr]
            run = paragraph.add_run(label)
            run.italic = True
            if not url.startswith("#") and "http" not in url:
                run.font.color.rgb = MUTED
        elif token.startswith("*") and token.endswith("*"):
            paragraph.add_run(token[1:-1]).italic = True
        position = match.end()
    if position < len(text):
        paragraph.add_run(text[position:])


def _paragraph(doc, text: str, *, style: str | None = None, italic: bool = False):
    paragraph = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    _inline_runs(paragraph, text)
    if italic:
        for run in paragraph.runs:
            run.italic = True
    return paragraph


def _repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _no_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    cant_split.set(qn("w:val"), "true")
    tr_pr.append(cant_split)


def _is_special(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or stripped.startswith(("#", "|", ">", "```"))
        or stripped == "---"
        or stripped.startswith("- ")
        or stripped.startswith("* ")
        or re.match(r"^\d+\.\s", stripped) is not None
    )


def _table(doc, header: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _repeat_header(table.rows[0])
    _no_split(table.rows[0])
    for index, name in enumerate(header):
        cell = table.rows[0].cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        _inline_runs(paragraph, name)
        for run in paragraph.runs:
            run.bold = True
            run.font.size = Pt(8.5)
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _shade(cell, "1D4ED8")
    for row_index, row in enumerate(rows):
        table_row = table.add_row()
        _no_split(table_row)
        cells = table_row.cells
        for column_index, value in enumerate(row[: len(header)]):
            cell = cells[column_index]
            cell.text = ""
            paragraph = cell.paragraphs[0]
            _inline_runs(paragraph, value)
            for run in paragraph.runs:
                run.font.size = Pt(8.5)
            if row_index % 2:
                _shade(cell, "F3F4F6")

    # Proportional column widths based on the longest content per column.
    content_width = 17.0
    weights: list[float] = []
    for column_index in range(len(header)):
        longest = len(header[column_index])
        for row in rows:
            if column_index < len(row):
                longest = max(longest, len(row[column_index]))
        weights.append(float(max(6, min(42, longest))))
    total = sum(weights)
    table.autofit = False
    for column_index, weight in enumerate(weights):
        width = Cm(content_width * weight / total)
        table.columns[column_index].width = width
        for cell in table.columns[column_index].cells:
            cell.width = width
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def convert(markdown: str, output: Path, title: str | None = None) -> Path:
    lines = markdown.splitlines()
    doc = Document()

    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(1.9)
    section.bottom_margin = Cm(1.8)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.08

    for level in range(1, 5):
        style = doc.styles[f"Heading {level}"]
        style.font.name = "Calibri"
        style.font.color.rgb = ACCENT if level <= 2 else INK
        style.font.size = Pt({1: 16, 2: 13.5, 3: 11.5, 4: 10.5}[level])
        style.font.bold = True

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run("VLM Annotate · Client meeting brief · 13 November 2026 · page ")
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED
    _add_page_number(footer)

    index = 0
    first_heading = True
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.4)
            paragraph.paragraph_format.space_before = Pt(2)
            paragraph.paragraph_format.space_after = Pt(6)
            for code_line in block:
                run = paragraph.add_run(code_line + "\n")
                run.font.name = "Consolas"
                run.font.size = Pt(8)
            index += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            header_cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            rows: list[list[str]] = []
            index += 1
            if index < len(lines) and re.match(r"^\|?[\s:\-|]+\|?$", lines[index].strip()):
                index += 1
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                rows.append(cells)
                index += 1
            _table(doc, header_cells, rows)
            continue

        if stripped.startswith("#"):
            match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
            if match:
                level = len(match.group(1))
                heading_text = match.group(2)
                if level == 1 and first_heading:
                    paragraph = doc.add_heading(level=0)
                    _inline_runs(paragraph, title or heading_text)
                    first_heading = False
                else:
                    paragraph = doc.add_heading(level=min(level, 4))
                    _inline_runs(paragraph, heading_text)
                index += 1
                continue

        if stripped == "---":
            doc.add_paragraph()
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip().lstrip(">").strip())
                index += 1
            paragraph = _paragraph(doc, " ".join(quote_lines), italic=True)
            paragraph.paragraph_format.left_indent = Cm(0.6)
            paragraph.paragraph_format.space_before = Pt(4)
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0x4B, 0x55, 0x63)
            continue

        bullet = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if bullet:
            indent = len(bullet.group(1))
            parts = [bullet.group(2)]
            index += 1
            while index < len(lines) and lines[index].startswith(" ") and not _is_special(lines[index]):
                parts.append(lines[index].strip())
                index += 1
            style = "List Bullet 2" if indent >= 2 else "List Bullet"
            _paragraph(doc, " ".join(parts), style=style)
            continue

        numbered = re.match(r"^(\s*)\d+\.\s+(.*)$", line)
        if numbered:
            parts = [numbered.group(2)]
            index += 1
            while index < len(lines) and lines[index].startswith(" ") and not _is_special(lines[index]):
                parts.append(lines[index].strip())
                index += 1
            _paragraph(doc, " ".join(parts), style="List Number")
            continue

        if not stripped:
            index += 1
            continue

        # Plain paragraph: join Markdown soft-wrapped continuation lines.
        parts = [stripped]
        index += 1
        while index < len(lines) and not _is_special(lines[index]):
            parts.append(lines[index].strip())
            index += 1
        _paragraph(doc, " ".join(parts))

    doc.core_properties.title = title or output.stem
    doc.core_properties.author = "VLM Annotate team"
    doc.core_properties.subject = "DSD 2026/2027 — Visage Technologies"
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    return output


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    source = Path(argv[1])
    target = Path(argv[2])
    title = argv[3] if len(argv) > 3 else None
    convert(source.read_text(encoding="utf-8"), target, title)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
