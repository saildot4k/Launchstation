"""Exercise the production IPv4 editor with scripted input and drawing stubs."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
widgets = (root / "src/dash_widgets.c").read_text()
header = (root / "include/dash_internal.h").read_text()


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
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef struct { u32 pressed; } DashInput;
'''
start = header.rfind("enum {", 0, header.index("DASH_IN_UP"))
code += header[start:header.index("};", start) + 2] + "\n"
code += r'''
static struct { u32 pressed, shoulders; } events[128];
static int count, index_, flushes, confirms, cancels;
static u32 shoulders;
static void push(u32 pressed, u32 repeat) {
    assert(count < 128);
    events[count].pressed = pressed;
    events[count++].shoulders = repeat;
}
static void dashInputPoll(DashInput *in) {
    assert(index_ < count);
    in->pressed = events[index_].pressed;
    shoulders = events[index_++].shoulders;
}
static u32 dashInputShoulderRepeat(void) { return shoulders; }
static void dashInputFlush(void) { flushes++; }
enum { DASH_SND_CURSOR, DASH_SND_CONFIRM, DASH_SND_CANCEL };
static void dashSoundPlay(int sound) {
    confirms += sound == DASH_SND_CONFIRM;
    cancels += sound == DASH_SND_CANCEL;
}
#define DASH_VW 640
#define DASH_VH 448
#define dashVisualUpdate() 0.016f
#define dashAnimSpeed() 1.0f
#define dashApproach(a,b,s,dt) (b)
#define dashEaseOutCubic(a) (a)
#define dashRenderScene(...) ((void)0)
#define dashModalBackdrop(...) ((void)0)
#define dashGfxPushAlpha(...) ((void)0)
#define dashGfxPushOffset(...) ((void)0)
#define dashModalPanel(...) ((void)0)
#define dashIcon(...) ((void)0)
#define dashTextS(...) 0.0f
#define dashTextFit(...) ((void)0)
#define dashDrawSelection(...) ((void)0)
#define dashPanel(...) ((void)0)
#define dashTextCenter(...) ((void)0)
#define dashDrawButton(...) 22.0f
#define dashModalHintRow(...) ((void)0)
#define dashGfxPopOffset(...) ((void)0)
#define dashGfxPopAlpha(...) ((void)0)
#define dashGfxPresent(...) ((void)0)
'''
code += function(widgets, "static void ipParse(")
code += function(widgets, "int dashModalIp(")
code += r'''
static void reset(void) {
    count = index_ = flushes = confirms = cancels = 0;
    shoulders = 0;
}
static void selectField(int field) {
    for (int i = 0; i < field; i++) push(DASH_IN_RIGHT, 0);
}
static void format(char out[16], const int oct[4]) {
    snprintf(out, 16, "%d.%d.%d.%d", oct[0], oct[1], oct[2], oct[3]);
}
static void accept(char buf[16], const int expected[4], const char *title) {
    char wanted[16]; format(wanted, expected);
    push(DASH_IN_OK, 0);
    assert(dashModalIp(title, NULL, buf, 16));
    assert(!strcmp(buf, wanted));
    assert(index_ == count && flushes == 2 && confirms == 1 && !cancels);
}
int main(void) {
    const char *titles[] = {"IP address", "Netmask", "Gateway"};
    const u32 buttons[] = {DASH_IN_UP, DASH_IN_DOWN, DASH_IN_R1,
                          DASH_IN_L1, DASH_IN_R2, DASH_IN_L2};
    const int steps[] = {1, -1, 10, -10, 10, -10};
    /* Every value and every field: wrapping must never carry into a neighbour. */
    for (int title = 0; title < 3; title++)
    for (int field = 0; field < 4; field++)
    for (int value = 0; value < 256; value++)
    for (int action = 0; action < 6; action++) {
        char buf[16]; int oct[] = {192, 0, 255, 1};
        reset(); oct[field] = value; format(buf, oct); selectField(field);
        push(buttons[action], 0);
        int next = value + steps[action];
        if (next > 255) next -= 256;
        if (next < 0) next += 256;
        oct[field] = next; accept(buf, oct, titles[title]);
    }
    /* An initial shoulder may appear in both channels; count it only once.
     * Further repeat events have no fresh press, as with a held L1/R1. */
    for (int direction = 0; direction < 2; direction++)
    for (int field = 0; field < 4; field++) {
        char buf[16]; int oct[] = {255, 0, 1, 250};
        u32 button = direction ? DASH_IN_R1 : DASH_IN_L1;
        reset(); format(buf, oct); selectField(field);
        push(button, button);
        for (int i = 0; i < 29; i++) {
            push(0, 0); /* Frames before the repeat delay must do nothing. */
            push(0, button);
        }
        int next = oct[field] + (direction ? 300 : -300);
        while (next < 0) next += 256;
        while (next > 255) next -= 256;
        oct[field] = next; accept(buf, oct, "IP address");
    }
    /* The existing left/right field wrap and Cancel behavior remain intact. */
    for (int field = 0; field < 4; field++)
    for (int cancel = 0; cancel < 2; cancel++) {
        char buf[16] = "192.168.0.1";
        reset(); selectField(field); push(DASH_IN_UP, 0);
        push(0, DASH_IN_R1);
        push(cancel ? DASH_IN_MENU : DASH_IN_BACK, 0);
        assert(!dashModalIp("Gateway", "Router address", buf, sizeof(buf)));
        assert(!strcmp(buf, "192.168.0.1"));
        assert(index_ == count && flushes == 2 && cancels == 1 && !confirms);
    }
    {
        char buf[16] = "192.168.0.255"; const int expected[] = {192,168,0,0};
        reset(); push(DASH_IN_LEFT, 0); push(DASH_IN_UP, 0);
        accept(buf, expected, "Gateway");
    }
    {
        char buf[16] = "0.255.255.0"; const int expected[] = {255,255,255,0};
        reset(); for (int i = 0; i < 4; i++) push(DASH_IN_RIGHT, 0);
        push(DASH_IN_DOWN, 0); accept(buf, expected, "Netmask");
    }
    puts("PASS: all 0-255 values wrap independently in all four IP/netmask/gateway fields; ten-point shoulder repeats, field navigation, confirm and cancel");
}
'''
compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("A host C compiler is required")
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / "ip_editor.c"
    executable = Path(directory) / "ip_editor"
    source.write_text(code)
    subprocess.run([compiler, "-std=c11", str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=10)
