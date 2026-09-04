"""Convert Markdown docs to printable PDFs (Chinese-capable).

Usage:
  python scripts/md_to_pdf_guide.py
  python scripts/md_to_pdf_guide.py docs/zh/features/FEATURE_LIST.md
  python scripts/md_to_pdf_guide.py docs/en/architecture/PROJECT_GUIDE.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = ROOT / "docs" / "zh" / "architecture" / "PROJECT_GUIDE.md"
DEFAULT_PDF = ROOT / "docs" / "zh" / "architecture" / "PROJECT_GUIDE.pdf"
FONT_PATH = Path(r"C:\Windows\Fonts\simhei.ttf")


class GuidePDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("CN", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"{self.page_no()}", align="C")


def _clean_inline(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = text.replace("> ", "")
    text = text.replace("👍", "[up]").replace("👎", "[down]")
    # Drop leftover non-BMP glyphs unsupported by SimHei
    text = "".join(ch for ch in text if ord(ch) < 0x10000)
    return text.strip()


def build_pdf(md: str, out: Path) -> None:
    pdf = GuidePDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("CN", fname=str(FONT_PATH))
    pdf.add_page()
    pdf.set_margins(16, 16, 16)

    in_code = False
    code_lines: list[str] = []
    table_rows: list[list[str]] = []

    def flush_code() -> None:
        nonlocal code_lines
        if not code_lines:
            return
        pdf.set_font("CN", size=8)
        pdf.set_fill_color(245, 245, 245)
        pdf.set_text_color(30, 30, 30)
        pdf.set_x(pdf.l_margin)
        block = "\n".join(code_lines)
        pdf.multi_cell(0, 4.2, block, fill=True)
        pdf.ln(2)
        code_lines = []
        pdf.set_text_color(0, 0, 0)
        pdf.set_x(pdf.l_margin)

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        # Skip markdown separator rows
        rows = [r for r in table_rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
        pdf.set_font("CN", size=8)
        usable = pdf.epw
        for i, row in enumerate(rows):
            cols = len(row) or 1
            col_w = usable / cols
            line_h = 5
            # Estimate height from tallest cell
            heights = []
            for cell in row:
                lines = pdf.multi_cell(col_w, line_h, cell, dry_run=True, output="LINES")
                heights.append(max(1, len(lines)) * line_h)
            row_h = max(heights) if heights else line_h
            if pdf.get_y() + row_h > pdf.page_break_trigger:
                pdf.add_page()
            x0 = pdf.get_x()
            y0 = pdf.get_y()
            if i == 0:
                pdf.set_fill_color(230, 236, 245)
            else:
                pdf.set_fill_color(255, 255, 255)
            for j, cell in enumerate(row):
                pdf.set_xy(x0 + j * col_w, y0)
                pdf.rect(x0 + j * col_w, y0, col_w, row_h)
                pdf.multi_cell(col_w, line_h, cell, border=0)
            pdf.set_xy(pdf.l_margin, y0 + row_h)
        pdf.ln(2)
        table_rows = []

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_table()
                in_code = True
            continue

        if in_code:
            cleaned = line.replace("\t", "  ")
            cleaned = cleaned.replace("👍", "[up]").replace("👎", "[down]")
            cleaned = "".join(ch for ch in cleaned if ord(ch) < 0x10000)
            code_lines.append(cleaned)
            continue

        if line.startswith("|") and line.endswith("|"):
            cells = [_clean_inline(c.strip()) for c in line.strip("|").split("|")]
            table_rows.append(cells)
            continue
        else:
            flush_table()

        if not line.strip():
            pdf.ln(2)
            continue

        if line.startswith("# "):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=18)
            pdf.multi_cell(0, 9, _clean_inline(line[2:]))
            pdf.ln(2)
        elif line.startswith("## "):
            pdf.ln(3)
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=14)
            pdf.set_text_color(20, 60, 120)
            pdf.multi_cell(0, 8, _clean_inline(line[3:]))
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
        elif line.startswith("### "):
            pdf.ln(2)
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=11)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 6.5, _clean_inline(line[4:]))
            pdf.set_text_color(0, 0, 0)
        elif line.startswith("#### "):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=10)
            pdf.multi_cell(0, 6, _clean_inline(line[5:]))
        elif line.startswith("---"):
            pdf.ln(1)
            y = pdf.get_y()
            pdf.set_draw_color(200, 200, 200)
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(3)
        elif line.startswith("- ") or line.startswith("* "):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=9)
            pdf.multi_cell(0, 5, "- " + _clean_inline(line[2:]))
        elif re.match(r"^\d+\.\s", line):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=9)
            pdf.multi_cell(0, 5, _clean_inline(line))
        elif line.startswith("> "):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=9)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(0, 5, _clean_inline(line[2:]))
            pdf.set_text_color(0, 0, 0)
        else:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("CN", size=9)
            pdf.multi_cell(0, 5, _clean_inline(line))

    flush_code()
    flush_table()
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))


def main() -> None:
    if not FONT_PATH.exists():
        raise SystemExit(f"Chinese font not found: {FONT_PATH}")

    args = sys.argv[1:]
    if not args:
        md_path, pdf_path = DEFAULT_MD, DEFAULT_PDF
    elif len(args) == 1:
        md_path = Path(args[0])
        if not md_path.is_absolute():
            md_path = ROOT / md_path
        pdf_path = md_path.with_suffix(".pdf")
    else:
        md_path = Path(args[0])
        pdf_path = Path(args[1])
        if not md_path.is_absolute():
            md_path = ROOT / md_path
        if not pdf_path.is_absolute():
            pdf_path = ROOT / pdf_path

    md = md_path.read_text(encoding="utf-8")
    build_pdf(md, pdf_path)
    print(f"Wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
