"""Exercise packaged payloads and the actual updater parser with hostile archives."""
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("packages", root / "scripts/package_apps.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
compiler = shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="app-packages-") as tmp:
    tmp = Path(tmp)
    elf = bytearray(6001)
    elf[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<H", elf, 18, 8)
    elf[52:] = bytes(i % 251 for i in range(len(elf) - 52))
    (tmp / "elf").write_bytes(elf)
    p.package(tmp / "elf", tmp / "elf", tmp / "out", "a" * 40, 1791500000)
    assert len(list((tmp / "out").iterdir())) == 4
    (tmp / "launchelf.h").write_text('''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#ifndef O_BINARY
#define O_BINARY 0
#endif
#define MAX_PATH 1024
#define MAX_NAME 256
#define FIO_O_RDONLY O_RDONLY
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_CREAT O_CREAT
#define FIO_O_TRUNC O_TRUNC
#define genOpen(p,f) open(p,(f)|O_BINARY,0600)
static inline int mock_close(int fd) {
    int output = (fcntl(fd, F_GETFL) & O_ACCMODE) == O_WRONLY;
    int result = close(fd);
    if(output && getenv("UPDATE_FAIL_CLOSE"))return -1;
    return result;
}
#define genClose mock_close
#define genLseek lseek
#define genRemove unlink
/* Deliberately short transfers exercise both retry loops. */
#define genRead(fd,p,n) read(fd,p,(n)>17?17:(n))
static inline int mock_write(int fd,const void *p,int n) {
    static int calls;
    if(getenv("UPDATE_FAIL_WRITE") && calls++ > 0)return -1;
    return write(fd,p,n>13?13:n);
}
#define genWrite mock_write
''')
    (tmp / "main.c").write_text('''
#include "launchelf.h"
#include "self_update.h"
int main(int argc,char **argv) {
    int fd=open(argv[1],O_RDONLY), size=lseek(fd,0,SEEK_END); close(fd);
    if(argc==5)
        printf("%d",selfUpdateExtractPsuTitle(argv[1],argv[2],size,argv[3]));
    else if(argc==4)
        printf("%d",selfUpdateExtractPsuSidecar(argv[1],argv[2],argv[3],size));
    else
        printf("%d",selfUpdateExtractPsu(argv[1],argv[2],size));
    return 0;
}
''')
    for index, (folder, name, _) in enumerate(p.VARIANTS):
        archive = (tmp / "out" / (folder + ".psu")).read_bytes()
        with zipfile.ZipFile(tmp / "out" / (folder + ".zip")) as z:
            assert set(z.namelist()) == {
                folder + "/" + filename for filename in
                (name, "title.cfg", "WLE-UPDATE-CA.PEM", "BGM.ADP")
            }
            assert z.read(folder + "/WLE-UPDATE-CA.PEM") == (root / "res/WLE-UPDATE-CA.PEM").read_bytes()
            assert z.read(folder + "/BGM.ADP") == (root / "res/music.sad").read_bytes()
            assert z.read(folder + "/" + name) == elf
            assert ("boot=" + name + "\n").encode() in z.read(folder + "/title.cfg")
        packaged_folder, packaged_members = p.inspect_psu(archive)
        assert packaged_folder == folder
        assert set(packaged_members) == {name, "title.cfg", "WLE-UPDATE-CA.PEM", "BGM.ADP"}
        assert packaged_members["WLE-UPDATE-CA.PEM"] == (root / "res/WLE-UPDATE-CA.PEM").read_bytes()
        assert packaged_members["BGM.ADP"] == (root / "res/music.sad").read_bytes()
        binary = tmp / ("parser" + str(index) + ".exe")
        subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-I" + str(tmp), "-I" + str(root / "include"),
                        *(["-DDS34"] if index else []), str(root / "src/update_psu.c"),
                        str(tmp / "main.c"), "-o", str(binary)], check=True)
        def check(data, good=False):
            path, stage = tmp / "candidate.psu", tmp / "stage.elf"
            path.write_bytes(data)
            result = int(subprocess.check_output([str(binary), str(path), str(stage)]))
            if good:
                assert result == len(elf) and stage.read_bytes() == elf
            else:
                assert result == -1 and not stage.exists()
        check(archive, True)
        def check_title(data, leaf, expected):
            path, stage = tmp / "title_candidate.psu", tmp / "title.stage"
            path.write_bytes(data)
            stage.unlink(missing_ok=True)
            got = int(subprocess.check_output([str(binary), str(path), str(stage), leaf, "title"]))
            if isinstance(expected, bytes):
                assert got == len(expected) and stage.read_bytes() == expected
                stage.unlink()
            else:
                assert got == expected and not stage.exists()
        cfg = packaged_members["title.cfg"]
        # A partially written or unfinalized metadata file cannot be published.
        for fault in ("UPDATE_FAIL_WRITE", "UPDATE_FAIL_CLOSE"):
            path, stage = tmp / "title_fault.psu", tmp / "title_fault.stage"
            path.write_bytes(archive)
            got = int(subprocess.check_output([str(binary), str(path), str(stage), name, "title"],
                                             env=dict(os.environ, **{fault: "1"})))
            assert got == -1 and not stage.exists()
        check_title(archive, name, cfg)
        check_title(archive, "BOOT.ELF", cfg.replace(("boot=" + name).encode(), b"boot=BOOT.ELF"))
        for invalid in ("", "../BOOT.ELF", "mc0:BOOT.ELF", "bad\\name", "bad\nname", "X" * 256):
            check_title(archive, invalid, -1)
        legacy_cfg = ("Title=New release\r\nboot=" + name + "\r\nVersion=new\r\n").encode()
        legacy_psu = p.make_psu(folder, {name: bytes(elf), "title.cfg": legacy_cfg}, bytes(8))
        check_title(legacy_psu, "custom.elf", legacy_cfg.replace(name.encode(), b"custom.elf"))
        for invalid in (b"Title=missing boot\n", b"boot=wrong.elf\n", cfg + b"boot=x\n",
                        cfg + b"\0", b"x" * 4097):
            check_title(p.make_psu(folder, {name: bytes(elf), "title.cfg": invalid}, bytes(8)), name, -1)
        check_title(p.make_psu(folder, {"title.cfg": cfg, name: bytes(elf)}, bytes(8))[:1536+512+len(cfg)-1], name, -1)
        # The native sidecar helper reads the already-verified PSU without
        # changing existing user files. Both assets stream under short IO.
        def check_sidecar(data, asset, expected):
            path, stage = tmp / "sidecar_candidate.psu", tmp / "sidecar.stage"
            path.write_bytes(data)
            stage.unlink(missing_ok=True)
            got = int(subprocess.check_output([str(binary), str(path), asset, str(stage)]))
            if isinstance(expected, bytes):
                assert got == len(expected) and stage.read_bytes() == expected
                stage.unlink()
            else:
                assert got == expected and not stage.exists()
        check_sidecar(archive, "WLE-UPDATE-CA.PEM",
                      (root / "res/WLE-UPDATE-CA.PEM").read_bytes())
        check_sidecar(archive, "BGM.ADP", (root / "res/music.sad").read_bytes())
        check_sidecar(archive, "wrong.name", -1)
        check_sidecar(archive[:-1], "BGM.ADP", -1)
        # The package parser validates names and lengths; the sidecar reader
        # additionally rejects invalid certificate/ADPCM payload signatures.
        invalid_ca = dict(packaged_members)
        invalid_ca["WLE-UPDATE-CA.PEM"] = b"X" * 64
        check_sidecar(p.make_psu(folder, invalid_ca, bytes(8)),
                      "WLE-UPDATE-CA.PEM", -1)
        invalid_bgm = dict(packaged_members)
        invalid_bgm["BGM.ADP"] = b"X" * 32
        check_sidecar(p.make_psu(folder, invalid_bgm, bytes(8)), "BGM.ADP", -1)
        check(archive[:-1])
        check(archive + b"trailing")
        bad = bytearray(archive); struct.pack_into("<I", bad, 4, 5); check(bad)
        bad = bytearray(archive); bad[64:64+448] = b"x" * 448; check(bad)
        bad = bytearray(archive); struct.pack_into("<I", bad, 1540, 0xffffffff); check(bad)
        bad = bytearray(archive); bad[1600:1600+448] = b"x" * 448; check(bad)
        check((tmp / "out" / (p.VARIANTS[1-index][0] + ".psu")).read_bytes())
        date = bytes(8)
        # Legacy two-file packages continue to work after the parser upgrade.
        check(p.make_psu(folder, {"title.cfg": b"boot=x\n", name: bytes(elf)}, date), True)
        check_sidecar(p.make_psu(folder, {"title.cfg": b"boot=x\n", name: bytes(elf)}, date),
                      "WLE-UPDATE-CA.PEM", 0)
        check_sidecar(p.make_psu(folder, {"title.cfg": b"boot=x\n", name: bytes(elf)}, date),
                      "BGM.ADP", 0)
        check(p.make_psu(folder, {name: bytes(elf), "wrong.cfg": b"x"}, date))
        # A partly bundled package, duplicate/unknown sidecar or corrupt record
        # must never result in an installed ELF.
        check(p.make_psu(folder, {name: bytes(elf), "title.cfg": b"x",
                                  "WLE-UPDATE-CA.PEM": b"x"}, date))
        check(p.make_psu(folder, {name: bytes(elf), "title.cfg": b"x",
                                  "WLE-UPDATE-CA.PEM": b"x", "bogus": b"x"}, date))
        # Duplicate ELF records, which a dictionary-based producer cannot represent.
        check(archive[:512] + archive[512:1536] + archive[1536:8192] * 2)
print("App package payloads and both native PSU parsers passed")
