"""Minimal deck renderer: one content model -> editable Markdown + PPTX.

Slide kinds
-----------
title, section, bullets, columns, table, kpi, quote, checklist

Content modules live in presentations/content/ and expose DECK (a dict).
Run:  .\\.venv\\Scripts\\python.exe presentations\\build_decks.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ACCENT = RGBColor(0x1D, 0x4E, 0xD8)
ACCENT_SOFT = RGBColor(0xDB, 0xEA, 0xFE)
INK = RGBColor(0x11, 0x18, 0x27)
MUTED = RGBColor(0x6B, 0x72, 0x80)
LINE = RGBColor(0xE5, 0xE7, 0xEB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
WARN = RGBColor(0xB4, 0x53, 0x09)

SLIDE_W = 13.333
SLIDE_H = 7.5
FONT = "Segoe UI"
FOOTER = "VLM Annotate · DSD 2026/2027"


def _textbox(slide, left, top, width, height, *, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    return box


def _paragraph(frame, text, *, size, bold=False, color=INK, space_before=0, space_after=6,
               align=PP_ALIGN.LEFT, first=False, level=0):
    paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
    paragraph.alignment = align
    paragraph.level = level
    paragraph.space_before = Pt(space_before)
    paragraph.space_after = Pt(space_after)
    run = paragraph.add_run()
    run.text = text
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return paragraph


def _background(slide, presentation):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = WHITE
    # top accent rule
    bar = slide.shapes.add_shape(1, Emu(0), Emu(0), presentation.slide_width, Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False


def _footer(slide, presentation, index, total, deck_title):
    _textbox(slide, 0.7, SLIDE_H - 0.5, 9.0, 0.3).text_frame  # spacer anchor
    footer = _textbox(slide, 0.7, SLIDE_H - 0.45, 9.5, 0.3)
    _paragraph(footer.text_frame, f"{FOOTER}   |   {deck_title}", size=9, color=MUTED, first=True)
    number = _textbox(slide, SLIDE_W - 1.4, SLIDE_H - 0.45, 0.7, 0.3)
    _paragraph(
        number.text_frame, f"{index}/{total}", size=9, color=MUTED, align=PP_ALIGN.RIGHT, first=True
    )


def _title_block(slide, title, section=None):
    if section:
        kicker = _textbox(slide, 0.7, 0.42, 11.9, 0.32)
        _paragraph(kicker.text_frame, section.upper(), size=11, bold=True, color=ACCENT, first=True)
        top = 0.78
    else:
        top = 0.55
    title_box = _textbox(slide, 0.7, top, 11.9, 0.95)
    _paragraph(title_box.text_frame, title, size=30 if len(title) < 55 else 26, bold=True, first=True)
    rule = slide.shapes.add_shape(1, Inches(0.7), Inches(top + 0.95), Inches(1.2), Inches(0.045))
    rule.fill.solid()
    rule.fill.fore_color.rgb = ACCENT
    rule.line.fill.background()
    rule.shadow.inherit = False


def _bullets(slide, bullets, left=0.7, top=1.9, width=11.9, height=4.9, size=20, gap=10):
    box = _textbox(slide, left, top, width, height)
    frame = box.text_frame
    for position, item in enumerate(bullets):
        level = 0
        text = item
        if isinstance(item, (tuple, list)):
            text, level = item[0], item[1]
        prefix = "•  " if level == 0 else "–  "
        _paragraph(
            frame,
            prefix + text,
            size=size if level == 0 else size - 4,
            color=INK if level == 0 else MUTED,
            space_before=0 if position == 0 else gap,
            first=position == 0,
            level=level,
        )


def _table(slide, columns, rows, *, left=0.7, top=2.0, width=11.9, height=4.4,
           col_widths=None, font_size=13):
    header_height = 0.5
    row_height = 0.46 if font_size >= 13 else 0.42
    total_height = min(height, header_height + row_height * len(rows))
    shape = slide.shapes.add_table(
        rows=len(rows) + 1, cols=len(columns), left=Inches(left), top=Inches(top),
        width=Inches(width), height=Inches(total_height),
    )
    table = shape.table
    table.rows[0].height = Inches(header_height)
    for row_index in range(1, len(rows) + 1):
        table.rows[row_index].height = Inches(row_height)
    if col_widths:
        total = sum(col_widths)
        for index, weight in enumerate(col_widths):
            table.columns[index].width = Emu(int(Inches(width) * weight / total))
    for column_index, name in enumerate(columns):
        cell = table.cell(0, column_index)
        cell.fill.solid()
        cell.fill.fore_color.rgb = ACCENT
        cell.margin_left = Inches(0.08)
        cell.margin_right = Inches(0.06)
        frame = cell.text_frame
        frame.word_wrap = True
        _paragraph(frame, name, size=font_size, bold=True, color=WHITE, first=True, space_after=0)
    for row_index, row in enumerate(rows, start=1):
        for column_index, value in enumerate(row):
            cell = table.cell(row_index, column_index)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if row_index % 2 else RGBColor(0xF9, 0xFA, 0xFB)
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.06)
            frame = cell.text_frame
            frame.word_wrap = True
            _paragraph(frame, str(value), size=font_size, first=True, space_after=0)
    return table


def _kpis(slide, cards):
    count = len(cards)
    gap = 0.25
    width = (11.9 - gap * (count - 1)) / count
    for index, card in enumerate(cards):
        left = 0.7 + index * (width + gap)
        shape = slide.shapes.add_shape(5, Inches(left), Inches(2.1), Inches(width), Inches(2.5))
        shape.fill.solid()
        shape.fill.fore_color.rgb = ACCENT_SOFT
        shape.line.color.rgb = ACCENT_SOFT
        shape.shadow.inherit = False
        value_box = _textbox(slide, left + 0.25, 2.3, width - 0.5, 0.9)
        _paragraph(value_box.text_frame, str(card["value"]), size=40, bold=True, color=ACCENT,
                   first=True, space_after=0)
        label_box = _textbox(slide, left + 0.25, 3.2, width - 0.5, 0.6)
        _paragraph(label_box.text_frame, card["label"], size=13, bold=True, first=True, space_after=2)
        detail_box = _textbox(slide, left + 0.25, 3.6, width - 0.5, 0.9)
        _paragraph(detail_box.text_frame, card.get("detail", ""), size=10.5, color=MUTED, first=True)


def _callout(slide, text, *, attribution=None, tone="info"):
    color = WARN if tone == "warn" else ACCENT
    box = slide.shapes.add_shape(5, Inches(0.7), Inches(2.05), Inches(11.9), Inches(2.7))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xFF, 0xF7, 0xED) if tone == "warn" else ACCENT_SOFT
    box.line.color.rgb = color
    box.line.width = Pt(1.25)
    box.shadow.inherit = False
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = Inches(0.45)
    frame.margin_right = Inches(0.45)
    frame.margin_top = Inches(0.4)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    _paragraph(frame, text, size=20, color=INK, first=True, space_after=0)
    if attribution:
        _paragraph(frame, attribution, size=11, color=MUTED, space_before=10)


def render_deck(deck: dict[str, Any], output: Path) -> Path:
    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_W)
    presentation.slide_height = Inches(SLIDE_H)
    blank = presentation.slide_layouts[6]
    slides = list(deck["slides"])
    # Every deck gets a cover slide even if the content module starts with a section.
    if not slides or slides[0].get("layout") != "title":
        slides.insert(
            0,
            {
                "layout": "title",
                "title": deck["title"],
                "subtitle": deck.get("subtitle", ""),
                "meta": deck.get("meta", []),
            },
        )
    total = len(slides)

    for index, spec in enumerate(slides, start=1):
        slide = presentation.slides.add_slide(blank)
        _background(slide, presentation)
        kind = spec.get("layout", "bullets")

        if kind == "title":
            band = slide.shapes.add_shape(1, Emu(0), Inches(1.65), presentation.slide_width,
                                          Inches(3.1))
            band.fill.solid()
            band.fill.fore_color.rgb = ACCENT
            band.line.fill.background()
            band.shadow.inherit = False
            title_box = _textbox(slide, 0.9, 1.9, 11.6, 1.5)
            _paragraph(title_box.text_frame, spec["title"], size=44, bold=True, color=WHITE,
                       first=True, space_after=8)
            subtitle_box = _textbox(slide, 0.9, 3.2, 11.6, 0.8)
            _paragraph(subtitle_box.text_frame, spec.get("subtitle", ""), size=20,
                       color=RGBColor(0xD1, 0xDB, 0xFA), first=True)
            meta_top = 5.2
            for line in spec.get("meta", []):
                meta_box = _textbox(slide, 0.9, meta_top, 11.6, 0.4)
                _paragraph(meta_box.text_frame, line, size=14, color=MUTED, first=True, space_after=2)
                meta_top += 0.42

        elif kind == "section":
            _paragraph(
                _textbox(slide, 0.9, 2.5, 11.5, 0.5).text_frame,
                spec.get("kicker", "SECTION").upper(), size=13, bold=True, color=ACCENT, first=True,
            )
            box = _textbox(slide, 0.9, 3.0, 11.5, 1.6)
            _paragraph(box.text_frame, spec["title"], size=40, bold=True, first=True)
            if spec.get("subtitle"):
                sub = _textbox(slide, 0.9, 4.7, 11.5, 0.9)
                _paragraph(sub.text_frame, spec["subtitle"], size=18, color=MUTED, first=True)

        elif kind == "bullets":
            _title_block(slide, spec["title"], spec.get("section"))
            _bullets(slide, spec["bullets"], size=spec.get("size", 20),
                     top=spec.get("top", 2.05))
            if spec.get("note"):
                note = _textbox(slide, 0.7, SLIDE_H - 1.05, 11.9, 0.5)
                _paragraph(note.text_frame, spec["note"], size=12, color=MUTED, first=True)

        elif kind == "columns":
            _title_block(slide, spec["title"], spec.get("section"))
            for side, left in (("left", 0.7), ("right", 6.85)):
                column = spec[side]
                heading = _textbox(slide, left, 1.95, 5.75, 0.45)
                _paragraph(heading.text_frame, column["heading"], size=16, bold=True, color=ACCENT,
                           first=True)
                _bullets(slide, column["bullets"], left=left, top=2.5, width=5.75, height=4.2,
                         size=15, gap=7)

        elif kind == "table":
            _title_block(slide, spec["title"], spec.get("section"))
            _table(
                slide,
                spec["columns"],
                spec["rows"],
                top=spec.get("top", 1.95),
                height=spec.get("height", 4.5),
                col_widths=spec.get("col_widths"),
                font_size=spec.get("font_size", 13),
            )
            if spec.get("note"):
                note = _textbox(slide, 0.7, SLIDE_H - 1.0, 11.9, 0.45)
                _paragraph(note.text_frame, spec["note"], size=11, color=MUTED, first=True)

        elif kind == "kpi":
            _title_block(slide, spec["title"], spec.get("section"))
            _kpis(slide, spec["cards"])
            if spec.get("note"):
                note = _textbox(slide, 0.7, 5.0, 11.9, 0.8)
                _paragraph(note.text_frame, spec["note"], size=13, color=MUTED, first=True)

        elif kind == "quote":
            _title_block(slide, spec["title"], spec.get("section"))
            _callout(slide, spec["text"], attribution=spec.get("attribution"),
                     tone=spec.get("tone", "info"))

        elif kind == "checklist":
            _title_block(slide, spec["title"], spec.get("section"))
            box = _textbox(slide, 0.7, 2.0, 11.9, 4.6)
            frame = box.text_frame
            for position, item in enumerate(spec["items"]):
                _paragraph(frame, f"☐  {item}", size=16, space_before=0 if position == 0 else 8,
                           first=position == 0)
        else:
            raise ValueError(f"unknown slide layout: {kind}")

        if spec.get("notes"):
            slide.notes_slide.notes_text_frame.text = spec["notes"]
        if kind != "title":
            _footer(slide, presentation, index, total, deck["short_title"])

    output.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(output)
    return output


def render_markdown(deck: dict[str, Any], output: Path) -> Path:
    lines: list[str] = [f"# {deck['title']}", ""]
    if deck.get("subtitle"):
        lines += [f"*{deck['subtitle']}*", ""]
    if deck.get("meta"):
        lines += deck["meta"] + [""]
    lines += ["---", ""]
    for index, spec in enumerate(deck["slides"], start=1):
        kind = spec.get("layout", "bullets")
        if kind == "title":
            continue  # already represented by the document header
        lines += [f"## {index}. {spec.get('title', '')}", ""]
        if spec.get("section"):
            lines += [f"*{spec['section']}*", ""]
        if kind in ("bullets", "checklist"):
            items = spec.get("bullets") or [f"☐ {item}" for item in spec.get("items", [])]
            for item in items:
                if isinstance(item, (tuple, list)):
                    text, level = item
                    lines.append(("  " * level) + f"- {text}")
                else:
                    lines.append(f"- {item}")
            lines.append("")
        elif kind == "columns":
            for side in ("left", "right"):
                lines += [f"**{spec[side]['heading']}**", ""]
                lines += [f"- {item}" for item in spec[side]["bullets"]] + [""]
        elif kind == "table":
            lines.append("| " + " | ".join(spec["columns"]) + " |")
            lines.append("|" + "|".join(["---"] * len(spec["columns"])) + "|")
            for row in spec["rows"]:
                lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
            lines.append("")
        elif kind == "kpi":
            for card in spec["cards"]:
                lines.append(f"- **{card['value']}** — {card['label']} ({card.get('detail', '')})")
            lines.append("")
        elif kind in ("quote", "section"):
            lines += [f"> {spec.get('text', spec.get('subtitle', ''))}", ""]
        if spec.get("note"):
            lines += [f"_{spec['note']}_", ""]
        if spec.get("notes"):
            lines += [f"<!-- speaker notes: {spec['notes']} -->", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
