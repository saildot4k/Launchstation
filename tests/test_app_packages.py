"""Exercise packaged payloads and the actual updater parser with hostile archives."""
import importlib.util
import datetime
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
    # Same Git identity must produce byte-identical packages on repeated runs.
    p.package(tmp / "elf", tmp / "elf", tmp / "repeat", "a" * 40, 1791500000)
    for archive in (tmp / "out").iterdir():
        assert archive.read_bytes() == (tmp / "repeat" / archive.name).read_bytes()
    # A later release must regenerate VERSION, using commit time rather than wall time.
    p.package(tmp / "elf", tmp / "elf", tmp / "next", "b" * 40, 1791500123)
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
    for index, (folder, name, title) in enumerate(p.VARIANTS):
        archive = (tmp / "out" / (folder + ".psu")).read_bytes()
        # A PSU restore takes the app folder's dates from its directory records.
        sas_date = struct.pack("<BBBBBBH", 0, 27, 0, 18, 31, 12, 2098)
        for directory_offset in (0, 512, 1024):
            directory = p.ENTRY.unpack_from(archive, directory_offset)
            assert directory[3] == directory[6] == sas_date
        # Every file restores with the same SAS creation and modification date.
        position = 1536
        while position < len(archive):
            entry = p.ENTRY.unpack_from(archive, position)
            assert entry[3] == entry[6] == sas_date
            position += 512 + (entry[2] + 1023) // 1024 * 1024
        with zipfile.ZipFile(tmp / "out" / (folder + ".zip")) as z:
            assert set(z.namelist()) == {
                folder + "/" + filename for filename in
                (name, "title.cfg", "WLE-UPDATE-CA.PEM", "BGM.ADP",
                 "icon.sys", "list.icn", "copy.icn", "del.icn", "APPINFO.PBT")
            }
            assert z.read(folder + "/WLE-UPDATE-CA.PEM") == (root / "res/WLE-UPDATE-CA.PEM").read_bytes()
            assert z.read(folder + "/BGM.ADP") == (root / "res/music.sad").read_bytes()
            assert z.read(folder + "/" + name) == elf
            assert ("boot=" + name + "\n").encode() in z.read(folder + "/title.cfg")
            zipped_members = {key.split("/", 1)[1]: z.read(key) for key in z.namelist()}
        packaged_folder, packaged_members = p.inspect_psu(archive)
        assert packaged_folder == folder
        assert packaged_members == zipped_members
        assets = root / "res/app"
        for asset in ("icon.sys", "list.icn", "copy.icn", "del.icn"):
            assert packaged_members[asset] == (assets / asset).read_bytes()
        assert len(packaged_members["icon.sys"]) == 964
        for icon in (b"list.icn\0", b"copy.icn\0", b"del.icn\0"):
            assert icon in packaged_members["icon.sys"]
        script = packaged_members["APPINFO.PBT"].decode()
        stamp = datetime.datetime.fromtimestamp(1791500000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fields = {"TITLE": title, "VERSION": f"aaaaaaa {stamp}", "ELF": name, "SAS": folder}
        for key, value in fields.items():
            assert script.splitlines().count(f'SET "{key}" "{value}"') == 1
        assert "@VERSION@" not in script and "433a2f04" not in script
        # All script logic and compatibility defaults remain as supplied.
        identity_prefixes = tuple(f'SET "{key}" ' for key in fields)
        assert [line for line in script.splitlines() if not line.startswith(identity_prefixes)] == [
            line for line in (assets / "APPINFO.PBT").read_text().splitlines()
            if not line.startswith(identity_prefixes)
        ]
        with zipfile.ZipFile(tmp / "next" / (folder + ".zip")) as z:
            later = z.read(folder + "/APPINFO.PBT").decode()
            next_stamp = datetime.datetime.fromtimestamp(1791500123, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            assert f'SET "VERSION" "bbbbbbb {next_stamp}"' in later
            assert f'SET "ELF" "{name}"' in later
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
        # Previously released four-file bundles stay accepted by both parsers.
        old_members = {key: packaged_members[key] for key in
                       (name, "title.cfg", "WLE-UPDATE-CA.PEM", "BGM.ADP")}
        old_archive = p.make_psu(folder, old_members, bytes(8))
        check(old_archive, True)
        # Each new companion is required, bounded, unique and recognized.
        for asset in ("APPINFO.PBT", "icon.sys", "list.icn", "copy.icn", "del.icn"):
            missing = dict(packaged_members); del missing[asset]
            check(p.make_psu(folder, missing, bytes(8)))
            unknown = dict(packaged_members); unknown["unknown"] = unknown.pop(asset)
            check(p.make_psu(folder, unknown, bytes(8)))
            invalid = dict(packaged_members); invalid[asset] = b""
            check(p.make_psu(folder, invalid, bytes(8)))
        for asset, length in (("APPINFO.PBT", 16385), ("icon.sys", 963),
                              ("list.icn", 1024 * 1024 + 1)):
            invalid = dict(packaged_members); invalid[asset] = b"x" * length
            check(p.make_psu(folder, invalid, bytes(8)))
        # Rename one same-length icon record to duplicate another without changing count.
        duplicate = bytearray(archive); pos = 1536
        while pos < len(duplicate):
            entry = p.ENTRY.unpack_from(duplicate, pos)
            if entry[-1].split(b"\0", 1)[0] == b"copy.icn":
                duplicate[pos + 64:pos + 73] = b"list.icn\0"
                break
            pos += 512 + (entry[2] + 1023) // 1024 * 1024
        check(duplicate)
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
        check_title(old_archive, name, cfg)
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
        check_sidecar(old_archive, "WLE-UPDATE-CA.PEM", old_members["WLE-UPDATE-CA.PEM"])
        check_sidecar(old_archive, "BGM.ADP", old_members["BGM.ADP"])
        check_sidecar(archive, "wrong.name", -1)
        check_sidecar(old_archive[:-1], "BGM.ADP", -1)
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
