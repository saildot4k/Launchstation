"""Settings help text must end above the footer hint bar.

Regression: with eight rows the two-line help started at y=380 and its second
line was drawn over the button hints (bar background starts at y=394).
"""
from source_groups import component_source
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
row_define = re.search(r"^#define DASH_LIST_ROW_H (.+)$", (root / "include/dash_internal.h").read_text(), re.M).group(1)
settings = component_source('src/dash_settings.c').replace("DASH_LIST_ROW_H", row_define)
ui = (root / "src/dash_ui.c").read_text(encoding="utf-8")

layout = (root / "include/dash_internal.h").read_text()
def number(name):
    return float(re.search(r"^#define " + name + r" ([\d.]+)f", layout, re.M).group(1))
footer_y = 448 - number("DASH_FOOTER_INSET")
pane_bottom = footer_y - 10
settings_bottom = pane_bottom - number("DASH_PANE_HELP_H")
geo = re.search(r"const float ix = [^,]+, iy = (\d+), irow = ([\d.]+)f?, iw = [^;]+;", settings)
iy, irow = float(geo.group(1)), float(geo.group(2))
rows = int((settings_bottom - iy + 3) / irow)
wrap = re.search(r"dashTextWrap\(ix, pane_bottom \+ (\d+), iw, (\d+), help, DASH_FS_CAPTION, DASH_C_TEXT3, (\d+)\)", settings)
gap, lines, line_h = (int(g) for g in wrap.groups())

hints = ui[ui.index("void dashDrawHints("):]
assert "float y = DASH_FOOTER_Y;" in hints
hint_y = footer_y
bar_top = hint_y - float(re.search(r"dashRectGradH\(x - 40, y - (\d+)", hints).group(1))

assert "#define ITEM_ROWS ((int)((DASH_PANE_B - DASH_PANE_HELP_H - 136.0f + 3.0f) /" in settings
assert iy + rows * irow - 3 <= settings_bottom
assert iy + (rows + 1) * irow - 3 > settings_bottom
help_bottom = settings_bottom + gap + lines * line_h
assert help_bottom <= pane_bottom
assert help_bottom <= bar_top, (help_bottom, bar_top)
print(f"PASS: settings help ends at y={help_bottom}, above the hint bar at y={bar_top:g}")

# Theme borders outline panels: with a transparent panel (Panels opacity 0)
# neither list boxes, cards nor the header strip may keep a floating border.
border_rule = ui[ui.index("static int panelBorderVisible(void)"):ui.index("void dashDrawSelection(")]
assert "return DASH_C_PANEL.a && DASH_C_BORDER.a;" in border_rule
assert border_rule.count("if (panelBorderVisible())") == 2
header = ui[ui.index("void dashDrawHeader("):ui.index("void dashDrawSectionTitle(")]
assert "if (DASH_C_PANEL.a && !DASH_C_BORDER.a && dashTheme.glow)" in header
print("PASS: panel borders disappear with transparent panels")

# The extra file row must leave a full status line above the same footer.
browser = (root / "src/dash_browser.c").read_text(encoding="utf-8")
row_define = re.search(r"^#define DASH_LIST_ROW_H (.+)$", (root / "include/dash_internal.h").read_text(), re.M).group(1)
browser = browser.replace("DASH_LIST_ROW_H", row_define)
assert "#define FB_ROWS ((int)((DASH_PANE_B - DASH_PANE_STATUS_H" in browser
file_y = float(re.search(r"#define FB_Y ([\d.]+)f", browser).group(1))
file_row_h = float(re.search(r"#define FB_ROW_H ([\d.]+)f", browser).group(1))
status_inset = float(re.search(r"status_y = DASH_PANE_B - ([\d.]+)f", browser).group(1))
status_y = pane_bottom - status_inset
file_bottom = pane_bottom - number("DASH_PANE_STATUS_H")
file_rows = int((file_bottom - file_y + 3) / file_row_h)
assert file_y + file_rows * file_row_h - 3 <= file_bottom
assert file_y + (file_rows + 1) * file_row_h - 3 > file_bottom
assert file_rows == 11
assert file_y + file_rows * file_row_h + 6 < status_y
assert status_y + 20 * 0.60 * 1.3 <= bar_top, (status_y, bar_top)
print("PASS: eleven file rows and footer status fit above the hint bar")

# All main split panes end at the shared bottom; full rows use all the room.
apps = (root / "src/dash_apps.c").read_text()
assert "#define LIST_ROWS ((int)((DASH_PANE_B - 104.0f + 3.0f) / LIST_ROW_H))" in apps
assert "DASH_PANE_B - (ly - 6), 14" in apps and "DASH_PANE_B - dy, 16" in apps
app_rows = int((pane_bottom - 104 + 3) / float(row_define[:-1]))
assert app_rows == 12 and rows == 9
for filename in ("dash_tools.c", "dash_files.c"):
    source = (root / "src" / filename).read_text()
    assert "pane_h = DASH_PANE_B - pane_y" in source
    assert "(int)((DASH_PANE_B - ly + 3.0f) / row_h)" in source
    assert "dy = pane_y, dw = DASH_PANE_R - dx, dh = pane_h" in source
hdd = (root / "src/dash_hdd.c").read_text()
assert "w = DET_W, h = DASH_PANE_B - y" in hdd
assert "DASH_PANE_B - (LIST_Y - 6), 14" in hdd
print("PASS: split panes share the footer limit; Applications fits 12 rows, Settings fits 9 with stable help, and File Browser reserves status space")
