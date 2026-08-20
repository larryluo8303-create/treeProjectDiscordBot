"""One-off script: convert docs/FEATURE_LIST.md -> docs/FEATURE_LIST.pdf

Uses fpdf2 with write_html().
Strips <code> tags (which force the non-CJK courier font) and replaces with backticks.
"""

import os
import re
import markdown
from fpdf import FPDF

# --- read & convert markdown to HTML ---
with open("docs/FEATURE_LIST.md", "r", encoding="utf-8") as f:
    md_text = f.read()

html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])

# Strip <code> tags — they force courier which can't render CJK
html_body = re.sub(r"<code>(.*?)</code>", r"`\1`", html_body)

# Replace emoji that CJK fonts can't render
html_body = html_body.replace("\U0001f534", "[!!!]")   # 🔴 → [!!!]
html_body = html_body.replace("\U0001f7e1", "[!!]")    # 🟡 → [!!]
html_body = html_body.replace("\U0001f7e2", "[!]")     # 🟢 → [!]
html_body = html_body.replace("\U0001f195", "[NEW]")   # 🆕 → [NEW]
# Strip remaining emoji that would cause encoding errors
html_body = re.sub(
    r"[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE0F\U0000200D"
    r"\U00002600-\U000026FF\U0000231A-\U0000231B\U00002934-\U00002935"
    r"\U000025AA-\U000025FE\U00002B05-\U00002B55\U0000203C-\U00003299]",
    "", html_body,
)

# --- find a CJK font on Windows ---
FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.expanduser("~\\AppData\\Local\\Microsoft\\Windows\\Fonts"),
]

CJK_CANDIDATES = [
    ("msyh.ttc", "msyhbd.ttc"),   # Microsoft YaHei
    ("simhei.ttf", "simhei.ttf"), # SimHei
    ("simsun.ttc", "simsun.ttc"), # SimSun
]

font_path = bold_path = None
for d in FONT_DIRS:
    for regular, bold in CJK_CANDIDATES:
        r = os.path.join(d, regular)
        b = os.path.join(d, bold)
        if os.path.isfile(r):
            font_path = r
            bold_path = b if os.path.isfile(b) else r
            break
    if font_path:
        break

if not font_path:
    raise FileNotFoundError("No CJK font found on this system")

print(f"Using font: {font_path}")

# --- build PDF ---
pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)

pdf.add_font("cjk", style="", fname=font_path)
pdf.add_font("cjk", style="B", fname=bold_path)
pdf.add_font("cjk", style="I", fname=font_path)
pdf.add_font("cjk", style="BI", fname=bold_path)

pdf.add_page()
pdf.set_font("cjk", size=10)

styled = '<font face="cjk" size="10">' + html_body + "</font>"

pdf.write_html(styled)
pdf.output("docs/FEATURE_LIST.pdf")
print("PDF generated: docs/FEATURE_LIST.pdf")
