"""Exercise production popup button/label geometry; no PS2 screenshot proof."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
ui = (root / "src/dash_ui.c").read_text()
header = (root / "include/dash_internal.h").read_text()
icons = (root / "include/dash_icons.h").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
typedef int DashColor;
#define DC(...) 0
#define DASH_C_TEXT 0
#define DASH_C_TEXT2 0
#define DASH_CORNER_SOFT 1
static struct { int corner; } dashTheme;
static struct { int icon_backing; } dashCfg;
static float expected_mid, width_scale;
static int icon_calls, text_calls, badge_calls;
static float dashTextWidth(const char *text, float scale) {
    return text ? strlen(text) * 10 * scale * width_scale : 0;
}
static void dashIcon(int icon, float x, float y, float size, DashColor color) {
    (void)icon; (void)x; (void)color;
    assert(fabsf(y + size * 0.5f - expected_mid) < 0.001f);
    icon_calls++;
}
static float dashTextS(float x, float y, const char *text, float scale, DashColor color) {
    (void)color;
    assert(fabsf(y + 16 * scale - expected_mid) < 0.001f);
    text_calls++;
    return x + dashTextWidth(text, scale);
}
static void dashPanelGradV(float x, float y, float w, float h, float radius,
                           DashColor top, DashColor bottom) {
    (void)x; (void)w; (void)radius; (void)top; (void)bottom;
    assert(fabsf(y + h * 0.5f - expected_mid) < 0.001f);
    badge_calls++;
}
static void dashPanelBorder(float x, float y, float w, float h, float radius, DashColor color) {
    (void)x; (void)y; (void)w; (void)h; (void)radius; (void)color;
}
'''
code += icons + "\n"
for macro in ("DASH_FS_SMALL", "DASH_FS_CAPTION", "DASH_SELECT_EXTRA_W"):
    code += re.search(r"^#define " + macro + r" .+$", header, re.M).group() + "\n"
for signature in ("float dashButtonTextY(", "static DashColor buttonColor(",
                  "static int keyIcon(", "static float buttonWidth(",
                  "static float drawButton(", "static void modalHintRow("):
    code += function(ui, signature)
code += r'''
int main(void) {
    const float origins[] = {40, 125.25f, 320, 400};
    const char *keys[] = {"L1", "L2", "L3", "R1", "R2", "R3", "START", "SELECT", "?"};
    for (int backing = 0; backing < 2; backing++) {
        dashCfg.icon_backing = backing;
        for (int fs = 90; fs <= 115; fs += 5) {
            width_scale = fs / 100.0f;
            for (unsigned y = 0; y < sizeof(origins) / sizeof(origins[0]); y++) {
                expected_mid = origins[y] + 11;
                for (int icon = DI_BTN_CROSS; icon <= DI_BTN_R3; icon++) {
                    drawButton(20, origins[y], icon, NULL);
                    dashTextS(70, dashButtonTextY(origins[y], DASH_FS_SMALL),
                              "Change", DASH_FS_SMALL, DASH_C_TEXT2);
                }
                for (unsigned key = 0; key < sizeof(keys) / sizeof(keys[0]); key++) {
                    dashTheme.corner = 2;
                    drawButton(20, origins[y], -1, keys[key]);
                    assert(dashTheme.corner == 2);
                }
                modalHintRow(20, origins[y], DI_BTN_CIRCLE, "Select", DI_BTN_CROSS, "Back");
                modalHintRow(20, origins[y], DI_BTN_CROSS, "Close", -1, NULL);
                modalHintRow(20, origins[y], -1, NULL, DI_BTN_CIRCLE, "Cancel");
            }
        }
    }
    assert(icon_calls && text_calls && badge_calls);
    puts("PASS: all controller glyphs, key badges, popup helper labels, both mappings/backings, font widths and fractional row positions share a centerline");
}
'''
compiler = shutil.which("gcc") or shutil.which("cc")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="popup-hint-alignment-") as folder:
    c = Path(folder) / "check.c"
    executable = Path(folder) / "check"
    c.write_text(code)
    subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                    str(c), "-o", str(executable), "-lm"], check=True)
    subprocess.run([str(executable)], check=True)

# Custom popup footers must use the same placement as shared menu hints.
for filename, labels in (
    ("dash_widgets.c", ("Change", "10", "Open", "Use this folder", "uLE:/ path", "Cancel")),
    ("dash_hdd.c", ("128 MB", "1 GB", "10 GB")),
    ("dash_settings_clock.c", ("Field", "Change", "10")),
):
    source = (root / "src" / filename).read_text()
    for label in labels:
        assert f'dashButtonTextY(hy, DASH_FS_SMALL), "{label}"' in source, (filename, label)
widgets = (root / "src/dash_widgets.c").read_text()
assert "const float text_y = dashButtonTextY(y, DASH_FS_SMALL);" in widgets
shell = (root / "src/dash_main.c").read_text()
assert "dashTextFit(bx, dashButtonTextY(by, DASH_FS_SMALL)" in shell
assert "dashButtonTextY(by + 3.0f, DASH_FS_SMALL), ok_label" in ui
assert "dashButtonTextY(by + 3.0f, DASH_FS_SMALL), cancel_label" in ui
print("PASS: menus, confirmations, keyboard, clock/IP/HDD editors, launch keys and picker use shared button/text alignment")
