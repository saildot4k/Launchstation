"""Reproduce missing/stale build metadata and prevent publishing anonymous ELFs."""
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = script("gen_githash")
checker = script("check_build_identity")
compiler = shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"
header = (root / "include/launchelf.h").read_text()
identity_include = header[header.index("#if defined(__has_include)"):header.index("//#define SIO_DEBUG")]

with tempfile.TemporaryDirectory(prefix="launchstation-build-identity-") as temp:
    temp = Path(temp)
    repo = temp / "checkout"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    def commit(text):
        (repo / "input").write_text(text)
        git("add", "input")
        git("-c", "user.name=Build identity test", "-c", "user.email=build@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", text)
        return git("rev-parse", "HEAD")

    git("init", "-q")
    first = commit("first")
    generated = repo / "githash.h"
    assert generator.generate(repo, generated, require_git=True) == first
    original = generated.read_bytes()
    assert f'#define GIT_HASH "{first}"'.encode() in original
    assert git("show", "-s", "--format=%cI", "HEAD").encode() in original
    unchanged_time = generated.stat().st_mtime_ns
    generator.generate(repo, generated, require_git=True)
    assert generated.stat().st_mtime_ns == unchanged_time
    second = commit("second")
    assert first != second
    generator.generate(repo, generated, require_git=True)
    assert second.encode() in generated.read_bytes() and first.encode() not in generated.read_bytes()

    # Compile the actual include/fallback block with and without a generated
    # header, for both controller variants. Do not redefine GIT_HASH in this test.
    def compiled_identity(directory):
        source = directory / "identity.c"
        source.write_text('#include <stdio.h>\n' + identity_include +
                          '\nint main(void) { puts(GIT_HASH); return 0; }\n')
        for flags in ([], ["-DDS34"]):
            binary = directory / "identity"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", *flags,
                            str(source), "-o", str(binary)], check=True)
            assert subprocess.check_output([str(binary)], text=True).strip() == (
                second if directory == repo else "local")

    compiled_identity(repo)
    archive = repo / "unpacked-source"
    archive.mkdir()
    # An archive inside another checkout must not inherit that checkout's ID.
    archive_header = archive / "githash.h"
    archive_header.write_bytes(original)
    try:
        generator.generate(archive, archive_header, require_git=True)
    except ValueError:
        pass
    else:
        raise AssertionError("Release build accepted an archive without its own Git metadata")
    assert archive_header.read_bytes() == original  # A strict failure never rewrites the header.
    assert generator.generate(archive, archive_header) == "local"
    compiled_identity(archive)
    archive_header.unlink()
    compiled_identity(archive)  # Reproduce the old PS2BUILD missing-header path.

    # Exercise the generator's real command-line root resolution too.
    (repo / "scripts").mkdir()
    shutil.copyfile(root / "scripts/gen_githash.py", repo / "scripts/gen_githash.py")
    generated.unlink()
    subprocess.run(["python3", str(repo / "scripts/gen_githash.py"), "--require-git"],
                   cwd=temp, check=True, stdout=subprocess.PIPE)
    assert second.encode() in generated.read_bytes()

    # The CI guard reads the unpacked executable rather than a header that
    # could be correct even if the compiler could not find it.
    elf = bytearray(52)
    elf[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HH", elf, 16, 2, 8)
    for name in ("standard.elf", "ds34.elf"):
        path = temp / name
        for identity in ("local", first, second):
            path.write_bytes(elf + identity.encode() + b"\0")
            try:
                checker.verify(path, second)
            except ValueError:
                assert identity != second
            else:
                assert identity == second
        path.write_bytes(elf + second.encode() + b"suffix\0")
        try:
            checker.verify(path, second)
        except ValueError:
            pass
        else:
            raise AssertionError("Unterminated revision was accepted")
    path.write_bytes(second.encode() + b"\0")
    try:
        checker.verify(path, second)
    except ValueError:
        pass
    else:
        raise AssertionError("Non-ELF was accepted")

workflow = (root / ".github/workflows/compile.yml").read_text()
generate = workflow.index("python3 scripts/gen_githash.py --require-git")
standard = workflow.index("      - name: Build Launchstation with ps2build")
ds34 = workflow.index("      - name: Build optional DS34 controller variant")
verify = workflow.index('python3 scripts/check_build_identity.py --revision "${GITHUB_SHA}"')
package = workflow.index("python3 scripts/package_apps.py")
assert generate < standard < ds34 < verify < package
assert "build/bin/wLaunchELF.elf build-ds34/bin/wLaunchELF.elf" in workflow[verify:package]
assert "python3 tests/test_build_identity.py" in workflow
makefile = (root / "Makefile").read_text()
assert "$(EE_OBJS): githash.h" in makefile
assert "githash.h: FORCE_GITHASH\n\tpython3 scripts/gen_githash.py" in makefile
print("PASS: full/stale/missing build identity, source-archive fallback, both variants and release gates")
