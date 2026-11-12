"""Exercise USB boot paths, startup driver loading and boot-file lookup.

Compile production functions in exFAT and legacy configurations. These mocks
check path selection and call ordering, not console/IOP hardware behavior.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/main_startup.c").read_text()


def extract(signature, text=source):
    start = text.index(signature)
    pos = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[pos] == "{") - (text[pos] == "}")
        pos += 1
    return text[start:pos] + "\n"


helpers = [
    "static int isDevicePathTerminator(char c)\\n{",
    "static int isBootUsbMassPath(const char *path)\\n{",
    "static int isBootAtaPath(const char *path)\\n{",
    "static int isBootHddPath(const char *path)\\n{",
    "static int isBootXfromPath(const char *path)\\n{",
    "static int isSlashRootedBootPathDevice(const char *path)\\n{",
    "static void normalizeBootPath(char *path)\\n{",
    "static void buildBootBlockPath(char *dst, size_t dst_size, const char *prefix, const char *partition, const char *path_part)\\n{",
    "enum BOOT_DEVICE prepareBootDeviceAndPath(const char *arg0, char *boot_path, size_t boot_path_len)\\n{",
    "void bringUpBootDeviceStack(enum BOOT_DEVICE boot_device)\\n{",
]
header = (root / "include/main_startup.h").read_text()
boot_enum = header[header.index("enum BOOT_DEVICE {"):header.index("};") + 2]
program = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 256
#define DPRINTF(...) ((void)0)
static char LaunchElfDir[MAX_PATH], LaunchElfBootDir[MAX_PATH], LastDir[MAX_PATH];
static int usb_loads, usb_ready_checks, exists_checks;
static char checked_ca[2][MAX_PATH];
static const char *present_ca;
static void loadUsbModules(void) { usb_loads++; }
static int prepareUsbRootBrowse(void) {
    assert(usb_loads == usb_ready_checks + 1);
    usb_ready_checks++;
    return 1;
}
static void loadHddModules(void) {}
#ifdef EXFAT
static void loadAtaModules(void) {}
#endif
static int wleExists(const char *path) {
    assert(exists_checks < 2);
    strcpy(checked_ca[exists_checks++], path);
    return present_ca && !strcmp(path, present_ca);
}
static int dashStoreBuildPath(char *path, int size, const char *file) {
    int n = snprintf(path, size, "mc0:/SYS-CONF/%s", file);
    return n > 0 && n < size ? 0 : -1;
}
"""
program += boot_enum + "\n"
program += "".join(extract(sig.replace("\\n", "\n")) for sig in helpers)
program += extract("static int launchstationUpdateCaPath(",
                   (root / "src/dash_tools.c").read_text())
program += r"""
static void normalized(const char *input, const char *expected) {
    char path[MAX_PATH];
    snprintf(path, sizeof(path), "%s", input);
    normalizeBootPath(path);
    assert(!strcmp(path, expected));
}
static void usbBoot(const char *input, const char *expected, const char *directory) {
    char path[MAX_PATH], ca[MAX_PATH], expected_ca[MAX_PATH];
    int before = usb_loads;
    assert(prepareBootDeviceAndPath(input, path, sizeof(path)) == BOOT_DEVICE_MASS);
    assert(!strcmp(path, expected));
    assert(!strcmp(LaunchElfDir, directory));
    assert(!strcmp(LaunchElfBootDir, directory));
    bringUpBootDeviceStack(BOOT_DEVICE_MASS);
    assert(usb_loads == before + 1 && usb_ready_checks == usb_loads);

    /* Config and BGM use these directories. A config fallback must not
     * redirect the CA lookup away from the running ELF's USB folder. */
    strcpy(LaunchElfDir, "mc1:/SYS-CONF/");
    snprintf(expected_ca, sizeof(expected_ca), "%sWLE-UPDATE-CA.PEM", directory);
    present_ca = expected_ca;
    exists_checks = 0;
    assert(launchstationUpdateCaPath(ca, sizeof(ca)));
    assert(!strcmp(ca, expected_ca) && exists_checks == 1);

    present_ca = "mc0:/SYS-CONF/WLE-UPDATE-CA.PEM";
    exists_checks = 0;
    assert(launchstationUpdateCaPath(ca, sizeof(ca)));
    assert(!strcmp(ca, present_ca) && exists_checks == 2);
    assert(!strcmp(checked_ca[0], expected_ca));
    assert(!strcmp(checked_ca[1], present_ca));
}
int main(void) {
    char input[MAX_PATH], expected[MAX_PATH], directory[32];
    normalized("usb0:APPS\\L.ELF", "usb0:/APPS/L.ELF");
    normalized("ata:APPS/L.ELF", "ata0:/APPS/L.ELF");
    normalized("mc0:APPS/L.ELF", "mc0:/APPS/L.ELF");
    normalized("mmce0:APPS/L.ELF", "mmce0:/APPS/L.ELF");
    normalized("mx4sio0:APPS/L.ELF", "mx4sio0:/APPS/L.ELF");
    normalized("hdd0:__common:pfs:/APPS/L.ELF", "hdd0:__common:pfs:/APPS/L.ELF");
    normalized("mass10:/APPS/L.ELF", "mass10:/APPS/L.ELF");
    normalized("", "");
    normalizeBootPath(NULL);
    for (int unit = 0; unit < 10; unit++) {
#ifdef EXFAT
        snprintf(directory, sizeof(directory), "usb%d:/APPS/", unit);
#else
        if (!unit) strcpy(directory, "mass:/APPS/");
        else snprintf(directory, sizeof(directory), "mass%d:/APPS/", unit);
#endif
        snprintf(expected, sizeof(expected), "%sL.ELF", directory);
        snprintf(input, sizeof(input), "mass%d:/APPS/L.ELF", unit);
        usbBoot(input, expected, directory);
        snprintf(input, sizeof(input), "mass%d:APPS\\L.ELF", unit);
        usbBoot(input, expected, directory);
    }
#ifdef EXFAT
    usbBoot("mass:/APPS/L.ELF", "usb0:/APPS/L.ELF", "usb0:/APPS/");
    usbBoot("mass0:L.ELF", "usb0:/L.ELF", "usb0:/");
#else
    usbBoot("mass:/APPS/L.ELF", "mass:/APPS/L.ELF", "mass:/APPS/");
    usbBoot("mass0:L.ELF", "mass:/L.ELF", "mass:/");
#endif
    usbBoot("usb1:/APPS/L.ELF", "usb1:/APPS/L.ELF", "usb1:/APPS/");
    puts("PASS: mass0-mass9 USB boot folders, USB driver readiness and CA lookup/fallback");
    return 0;
}
"""
compiler = shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Host gcc or clang required")
with tempfile.TemporaryDirectory(prefix="launchstation-usb-boot-") as tmp:
    c = Path(tmp) / "boot.c"
    exe = Path(tmp) / "boot"
    c.write_text(program)
    for variant in ("exfat", "legacy"):
        flags = ["-DEXFAT=1"] if variant == "exfat" else []
        subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror", *flags,
                        str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=5)
