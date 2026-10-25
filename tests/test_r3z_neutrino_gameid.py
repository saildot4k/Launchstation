"""Behavioral R3Z 4.80 ISO/SYSTEM.CNF and MMCE VMC regression.

Compiles the actual neutrino_gameid.c against POSIX file/Devctl stubs, then
exercises valid/malformed ISO9660 images and the R3Z 4.80 slot policy.
Reference: saildot4k/wLaunchELF_R3Z tag 4.80, commit
39fb5bc7700b0d9bf9ed8448f4b9f080b08d81d7, src/neutrino_gameid.c.
An mmceN: file is on the SD filesystem; only an mcN: Neutrino ELF
excludes its emulated-card slot. MX4SIO sources/loaders are excluded.
"""
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GAMEID = (ROOT / "src/neutrino_gameid.c").read_text(encoding="utf-8")
NEUTRINO = (ROOT / "src/neutrino_iso.c").read_text(encoding="utf-8")
BUILD = (ROOT / "ps2.yaml").read_text(encoding="utf-8")
MAKE = (ROOT / "Makefile").read_text(encoding="utf-8")

assert "neutrino_gameid.o" in MAKE
assert "src/neutrino_gameid.c" in BUILD
assert "loadMmceModules(" not in GAMEID, "ID lookup must never reboot/replace storage"
assert "load_udpfs(" not in GAMEID
assert "showNeutrinoLaunchOptions(&options)" in NEUTRINO
assert "prepareNeutrinoGameID(opened_iso" in NEUTRINO
assert "displayRetroGemGameID(gameID, 2);" in NEUTRINO
assert "setNeutrinoMmceGameID(gameID, opened_iso, fullpath);" in NEUTRINO
assert NEUTRINO.index("prepareNeutrinoGameID(opened_iso") < NEUTRINO.index("prepareNeutrinoCandidateLaunch(&candidates")
assert NEUTRINO.index("setNeutrinoMmceGameID(gameID") < NEUTRINO.index("CleanUpForKeepIopExec(")
assert NEUTRINO.index("displayRetroGemGameID(gameID, 2);") > NEUTRINO.index("CleanUpForKeepIopExec(")

def iso_fixture(path, cnf: bytes, valid=True):
    sectors = bytearray(23 * 2048)
    pvd = 16 * 2048
    sectors[pvd] = 1
    sectors[pvd+1:pvd+6] = b"CD001" if valid else b"BROKN"
    sectors[pvd+6] = 1
    sectors[pvd+156] = 34
    sectors[pvd+158:pvd+162] = struct.pack("<I", 20)
    sectors[pvd+166:pvd+170] = struct.pack("<I", 2048)
    sectors[pvd+181] = 2

    # Root directory has a real ISO9660 SYSTEM.CNF;1 extent at LBA 21.
    root = 20 * 2048
    sectors[root] = 34
    sectors[root+25] = 2
    sectors[root+32] = 1
    sectors[root+33] = 0
    file = root + 34
    sectors[file] = 46
    sectors[file+2:file+6] = struct.pack("<I", 21)
    sectors[file+10:file+14] = struct.pack("<I", len(cnf))
    sectors[file+32] = 12
    sectors[file+33:file+45] = b"SYSTEM.CNF;1"
    sectors[21*2048:21*2048+len(cnf)] = cnf
    path.write_bytes(sectors)

prefix = r"""
#define MMCE 1
#define MX4SIO 1
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include "neutrino_gameid.h"
typedef unsigned int u32;
typedef long long s64;
static FILE *iso;
static int stack_present = 0;
static int calls, pings, delays, polls, loads;
static int ping_mask, set_mask, status_mask;
static int ping_error_mask, set_error_mask, status_result;
static int read_limit, read_error, seek_error;
enum {STORAGE_STACK_DEFAULT, STORAGE_STACK_MMCE, STORAGE_STACK_MX4SIO};
static int storage_driver_stack_mode, mx4sio_driver_running;
static int wle_ascii_tolower(int c) { return c >= 'A' && c <= 'Z' ? c + ('a'-'A') : c; }
int openPathForRead(const char *path, char *out, size_t out_size) {
    (void)out; (void)out_size;
    iso = fopen(path, "rb");
    return iso ? 1 : -1;
}
s64 genLseek(int fd, s64 where, int how) {
    (void)fd;
    if (seek_error) return -1;
    if (fseek(iso, (long)where, how)) return -1;
    return ftell(iso);
}
int genRead(int fd, void *buffer, int count) {
    (void)fd;
    if (read_error) return 0;
    if (read_limit && count > read_limit) count = read_limit;
    return (int)fread(buffer, 1, count, iso);
}
void genClose(int fd) { (void)fd; fclose(iso); iso = NULL; }
int loadMmceModules(void) {
    loads++;
    if (stack_present) storage_driver_stack_mode = STORAGE_STACK_MMCE;
    return stack_present;
}
int fileXioDevctl(const char *device, int cmd, void *arg, int arglen, void *out, int outlen) {
    int port, mask;
    assert(!strncmp(device,"mmce",4) && device[5]==':' && device[6]==0);
    port=device[4]-'0';assert(port==0 || port==1);mask=1<<port;
    (void)out; (void)outlen;
    if (cmd == 1) {
        assert(!arg && !arglen);pings++;ping_mask|=mask;
        return (ping_error_mask & mask) ? -1 : 0;
    }
    if (cmd == 8) {
        assert(arglen == NEUTRINO_GAME_ID_SIZE && !strcmp(arg, "SLUS_123.45"));
        assert(ping_mask & mask);calls++;set_mask|=mask;
        return (set_error_mask & mask) ? -1 : 0;
    }
    assert(cmd == 2 && (set_mask & mask) && !arg && !arglen);
    polls++;status_mask|=mask;return status_result;
}
void DelayThread(int usec) { assert(usec == 1000000); delays++; }
#define DPRINTF(...) ((void)0)
"""
init = (ROOT / "src/init.c").read_text()
start = init.index("int loadMmceModulesForGameID(void)")
end = init.index("\n}\n", start) + 3
code = init[start:end] + (
    GAMEID.replace('#include "launchelf.h"', "")
          .replace('#include "popstarter_internal.h"', "")
          .replace('#include "neutrino_gameid.h"', "")
)
main = r"""
static void reset_mmce(void) {
    calls=pings=delays=polls=loads=0;
    ping_mask=set_mask=status_mask=0;
    ping_error_mask=set_error_mask=status_result=0;
    stack_present=1;storage_driver_stack_mode=STORAGE_STACK_DEFAULT;
    mx4sio_driver_running=0;
}
static int count_slots(int mask) { return (mask & 1)+((mask>>1)&1); }
int main(int argc, char **argv) {
    char id[12];
    assert(argc >= 4);
    assert(prepareNeutrinoGameID(argv[1], id, sizeof(id)) == 1);
    assert(strcmp(id, "SLUS_123.45") == 0);
    assert(iso == NULL);
    for (int i=2; i<argc; i++) {
        strcpy(id, "SLUS_123.45");
        assert(prepareNeutrinoGameID(argv[i], id, sizeof(id)) == 0);
        assert(id[0] == '\0' && iso == NULL);
    }
    read_limit = 11; /* Complete fragmented reads, not just sector-sized reads. */
    assert(prepareNeutrinoGameID(argv[1], id, sizeof(id)) == 1 && iso == NULL);
    read_error = 1;
    assert(!prepareNeutrinoGameID(argv[1], id, sizeof(id)) && !id[0] && iso == NULL);
    read_error = 0; seek_error = 1;
    assert(!prepareNeutrinoGameID(argv[1], id, sizeof(id)) && !id[0] && iso == NULL);
    seek_error = read_limit = 0;
    assert(prepareNeutrinoGameID(argv[1], id, sizeof(id)-1) == 0);
    assert(prepareNeutrinoGameID(argv[1], NULL, 0) == 0);

    /* Expected masks are sourced from the pinned R3Z 4.80 implementation.
     * Neither an ISO nor an ELF on mmceN: excludes an emulated-card slot. */
    static const char *const isos[]={
        "usb0:/GAME.iso", "mass:/GAME.iso", "mass1:/GAME.iso",
        "ata0:/GAME.iso", "ata1:/GAME.iso", "udpfs:/GAME.iso",
        "mmce0:/GAME.iso", "mmce1:/GAME.iso", "mmce:/GAME.iso",
        "mx4sio:/GAME.iso", "mx4sio0:/GAME.iso"
    };
    static const struct {const char *path;int mask;} elfs[]={
        {"mass0:/NEUTRINO.ELF",3}, {"usb1:/NEUTRINO.ELF",3},
        {"ata0:/N.ELF",3}, {"ata1:/N.ELF",3}, {"udpfs:/N.ELF",3},
        {"mmce0:/N.ELF",3}, {"mmce1:/N.ELF",3}, {"mmce:/N.ELF",3},
        {"mc0:/N.ELF",2}, {"mc1:/N.ELF",1}, {"mc:/N.ELF",3},
        {"mx4sio:/N.ELF",0}, {"mx4sio0:/N.ELF",0}
    };
    for (unsigned i=0;i<sizeof(isos)/sizeof(*isos);i++) {
        for (unsigned j=0;j<sizeof(elfs)/sizeof(*elfs);j++) {
            int eligible=i>=9 ? 0 : elfs[j].mask;
            for (int present=0;present<4;present++) {
                reset_mmce();ping_error_mask=(~present)&3;
                setNeutrinoMmceGameID("SLUS_123.45",isos[i],elfs[j].path);
                assert(ping_mask==eligible && pings==count_slots(eligible));
                assert(set_mask==(eligible & present));
                assert(calls==count_slots(set_mask));
                assert(status_mask==set_mask && polls==calls && delays==calls);
                assert(loads==(eligible!=0));
            }
        }
    }
    /* A resident MX4SIO stack also excludes switching even for USB paths. */
    reset_mmce();mx4sio_driver_running=1;
    storage_driver_stack_mode=STORAGE_STACK_MX4SIO;
    setNeutrinoMmceGameID("SLUS_123.45","usb0:/GAME.iso","mass0:/N.ELF");
    assert(!loads && !calls && !pings && !polls && !delays);
    reset_mmce();stack_present=0;
    setNeutrinoMmceGameID("SLUS_123.45","usb0:/GAME.iso","mass0:/N.ELF");
    assert(loads==1 && !calls && !pings && !polls && !delays);
    reset_mmce();
    setNeutrinoMmceGameID("bad","usb0:/GAME.iso","mass0:/N.ELF");
    setNeutrinoMmceGameID(NULL,"usb0:/GAME.iso","mass0:/N.ELF");
    setNeutrinoMmceGameID("SLUS_123.45",NULL,"mass0:/N.ELF");
    setNeutrinoMmceGameID("SLUS_123.45","usb0:/GAME.iso",NULL);
    assert(!loads && !calls && !pings);
    /* Each adapter fails independently; no waits without an accepted SET. */
    reset_mmce();set_error_mask=1;
    setNeutrinoMmceGameID("SLUS_123.45","mmce0:/GAME.iso","mmce0:/N.ELF");
    assert(ping_mask==3 && set_mask==3 && calls==2);
    assert(status_mask==2 && polls==1 && delays==1);
    reset_mmce();set_error_mask=3;
    setNeutrinoMmceGameID("SLUS_123.45","mmce0:/GAME.iso","mmce0:/N.ELF");
    assert(calls==2 && !polls && !delays);
    reset_mmce();status_result=-1;
    setNeutrinoMmceGameID("SLUS_123.45","mmce0:/GAME.iso","mass0:/N.ELF");
    assert(polls==2 && delays==2);
    reset_mmce();status_result=1;
    setNeutrinoMmceGameID("SLUS_123.45","mmce0:/GAME.iso","mass0:/N.ELF");
    assert(polls==30 && delays==30); /* 15 polls per responding adapter. */
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="launchstation-r3z-gameid-") as td:
    temp = Path(td)
    valid = temp / "game.iso"
    malformed = temp / "malformed.iso"
    missing = temp / "missing.iso"
    iso_fixture(valid, b"BOOT2 = cdrom0:\\SLUS_123.45;1\r\nVER = 1.00\r\n")
    iso_fixture(malformed, b"BOOT2 = cdrom0:\\SLUS_123.45;1\r\n", valid=False)
    iso_fixture(missing, b"BOOT2 = cdrom0:\\NOT_A_GAME;1\r\n")
    invalid = [malformed, missing]
    original = valid.read_bytes()
    # Mutate on-disk lengths/extents, not parser implementation details.
    pvd, record = 16 * 2048, 20 * 2048 + 34
    mutations = [
        (pvd + 158, struct.pack("<I", 0xffffffff)),  # root outside image
        (pvd + 166, struct.pack("<I", 0xffffffff)),  # root size exceeds image
        (record, b"\x21"),                         # short directory record
        (record + 32, b"\xff"),                    # name exceeds record
        (record + 2, struct.pack("<I", 0xffffffff)), # CNF outside image
        (record + 10, struct.pack("<I", 4097)),      # oversized CNF
        (record + 10, struct.pack("<I", 0)),         # empty CNF
        (record + 25, b"\x80"),                    # unsupported multi-extent CNF
        (record + 26, b"\x01"),                    # unsupported interleave
    ]
    for i, (offset, value) in enumerate(mutations):
        image = bytearray(original)
        image[offset:offset + len(value)] = value
        path = temp / f"invalid-{i}.iso"
        path.write_bytes(image)
        invalid.append(path)
    truncated = temp / "truncated.iso"
    truncated.write_bytes(original[:pvd + 100])
    invalid.extend([truncated, temp / "nonexistent.iso"])
    (temp / "test.c").write_text(prefix + code + main, encoding="utf-8")
    binary = temp / "neutrino_gameid_test"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "include"), str(temp / "test.c"),
                    "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(valid), *map(str, invalid)], check=True, timeout=10)

print("R3Z 4.80 Neutrino: ISO parsing, MMCE SD sources/loaders, emulated MC slot exclusion, MX4SIO exclusion and bounded failures passed")
