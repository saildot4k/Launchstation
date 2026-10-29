"""Execute the production Ember path parser against real tester-style paths."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "src/ember.c").read_text(encoding="utf-8")

def function(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"

code = r"""
#include <assert.h>
#include <ctype.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#define MAX_PATH 1024
#define EMBER_NAME_MAX 180
static struct { char ember_dir[MAX_PATH]; } config, *setting=&config;
static char checked_elf[MAX_PATH];
static int readable=1,checks;
static int readableElf(const char *path) {
    checks++;snprintf(checked_elf,sizeof(checked_elf),"%s",path);return readable;
}

static int wle_ascii_tolower(int c) { return tolower((unsigned char)c); }
static int genCmpFileExt(const char *filename, const char *extension)
{
    const char *p = strrchr(filename, '.');
    if (p == NULL) return 0;
#ifdef _WIN32
    return _stricmp(p + 1, extension) == 0;
#else
    return strcasecmp(p + 1, extension) == 0;
#endif
}
"""
for sig in (
    "static int isSep(",
    "static int segmentCaseEqual(",
    "static int emberExt(",
    "static int parseEmberGamePath(",
    "static char pathSep(",
    "static int appendFile(",
    "static int configuredEmberElf(",
):
    code += function(src, sig)

code += r"""
static void expect_ok(const char *path, const char *want_root, const char *want_game)
{
    char root[MAX_PATH], game[EMBER_NAME_MAX + 1];
    assert(parseEmberGamePath(path, root, sizeof(root), game, sizeof(game)));
    assert(!strcmp(root, want_root));
    assert(!strcmp(game, want_game));
}

int main(void)
{
    /* The selected executable can have any ELF name. Older folder-valued
     * EMBER_DIR configurations still resolve to their local ember.elf. */
    char configured[MAX_PATH];
    strcpy(config.ember_dir,"usb1:/Launchers/My Ember.ELF");
    assert(configuredEmberElf(configured,sizeof(configured)));
    assert(!strcmp(configured,"usb1:/Launchers/My Ember.ELF"));
    assert(!strcmp(checked_elf,configured));
    int before=checks;
    assert(!configuredEmberElf(configured,8) && checks==before);
    assert(!configuredEmberElf(configured,0) && checks==before);
    assert(!configuredEmberElf(NULL,sizeof(configured)) && checks==before);
    readable=0;assert(!configuredEmberElf(configured,sizeof(configured)));readable=1;
    strcpy(config.ember_dir,"usb0:/My Ember/");
    assert(configuredEmberElf(configured,sizeof(configured)));
    assert(!strcmp(configured,"usb0:/My Ember/ember.elf"));
    strcpy(config.ember_dir,"mass3:\\My Ember");
    assert(configuredEmberElf(configured,sizeof(configured)));
    assert(!strcmp(configured,"mass3:\\My Ember\\ember.elf"));
    config.ember_dir[0]='\0';assert(!configuredEmberElf(configured,sizeof(configured)));
    setting=NULL;assert(!configuredEmberElf(configured,sizeof(configured)));setting=&config;

    /* Exact layout and punctuation from the hardware tester report. */
    expect_ok(
        "usb0:/EMBER/games/eFootball 2026 (ZWE)/eFootball 2026 (ZWE).cue",
        "usb0:/EMBER", "eFootball 2026 (ZWE)");

    /* Extension and games segment are case-insensitive. */
    expect_ok(
        "mass3:/My Ember/GAMES/Crash Bandicoot (USA)/disc 1.CUE",
        "mass3:/My Ember", "Crash Bandicoot (USA)");

    /* Windows-style separators are accepted too because device paths can be
       normalized by callers before reaching the parser. */
    expect_ok(
        "usb1:\\EMBER\\games\\Spyro 2 (Europe)\\Spyro 2 (Europe).bin",
        "usb1:\\EMBER", "Spyro 2 (Europe)");

    {
        char root[MAX_PATH], game[EMBER_NAME_MAX + 1];
        assert(!parseEmberGamePath(
            "usb0:/EMBER/eFootball 2026 (ZWE).cue",
            root, sizeof(root), game, sizeof(game)));
        assert(!parseEmberGamePath(
            "usb0:/EMBER/games/eFootball 2026 (ZWE)/disc/subdir/game.cue",
            root, sizeof(root), game, sizeof(game)));
        assert(!parseEmberGamePath(
            "usb0:/POPS/eFootball 2026 (ZWE).vcd",
            root, sizeof(root), game, sizeof(game)));
    }

    puts("PASS: production Ember parser accepts tester CUE/BIN paths with spaces and parentheses");
    return 0;
}
"""

compiler = shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Host gcc or clang required")

with tempfile.TemporaryDirectory(prefix="ember-paths-") as tmp:
    source = Path(tmp) / "ember_paths.c"
    exe = Path(tmp) / "ember_paths"
    source.write_text(code, encoding="utf-8")
    subprocess.run([compiler, "-std=gnu11", str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
