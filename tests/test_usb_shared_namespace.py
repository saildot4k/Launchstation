"""Exercise Launchstation's real dashboard USB/shared-BDM path gates in EXFAT builds.

This is a deterministic host harness, not a console/IOP hardware simulation.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/dash_devices.c").read_text()


def extract(signature):
    begin = source.index(signature)
    pos = source.index("{", begin) + 1
    depth = 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[begin:pos] + "\n"


program = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define EXFAT 1
#define DASH_DEV_ABSENT 0
#define DASH_DEV_PROBE 1
#define SCECdNODISC 0

static int vmcMounted[2], cdmode, uLE_cdmode;
static int bdm_ready, usb_ready, usb_mask;

static int filerRootMcPresent(int port, void *type, void *free_kb) {
    (void)port; (void)type; (void)free_kb; return 0;
}
static int isUsbMassStackLoaded(void) { return usb_ready; }
static int filerUsbDriveMask(void) { return usb_mask; }
static int storageState(const char *path) {
    (void)path; return DASH_DEV_PROBE;
}
static int isPathDeviceStackLoaded(const char *path) {
    (void)path; return bdm_ready;
}
static int isPcCardCfPath(const char *path) {
    (void)path; return 0;
}
static int isPcCardCfOnline(void) {
    return 0;
}
"""
program += extract("int dashDevicePathReady(const char *path)\n{")
program += r"""
int main(void) {
    bdm_ready=1; usb_ready=0; usb_mask=0;
    assert(dashDevicePathReady("mass0:/APPS/one.elf"));
    assert(dashDevicePathReady("mass9:/APPS/two.elf"));
    assert(!dashDevicePathReady("mass:/APPS/one.elf"));
    assert(!dashDevicePathReady("usb0:/APPS/one.elf"));
    bdm_ready=0;
    assert(!dashDevicePathReady("mass2:/APPS/two.elf"));
    bdm_ready=1; usb_ready=1; usb_mask=1;
    assert(dashDevicePathReady("usb0:/APPS/one.elf"));
    assert(!dashDevicePathReady("usb1:/APPS/one.elf"));
    assert(dashDevicePathReady("mass:/APPS/one.elf"));
    puts("PASS: numbered shared BDM slots are not misidentified as USB");
    return 0;
}
"""
compiler = shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Host gcc or clang required")
with tempfile.TemporaryDirectory(prefix="launchstation-bdm-paths-") as tmp:
    c = Path(tmp) / "identity.c"
    exe = Path(tmp) / "identity"
    c.write_text(program)
    subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=5)
