"""Build the actual EE FTP lifecycle and screen against a mocked IOP transport."""
from pathlib import Path
import os
import shutil
import shlex
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
cc=os.environ.get("CC") or shutil.which("gcc") or shutil.which("clang")
assert cc,"Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-ftp-session-") as tmp:
    exe=Path(tmp)/"session"
    subprocess.run([cc,*shlex.split(os.environ.get("CFLAGS","")),"-DETH","-std=c11","-Wall","-Wextra","-Werror",
                    "-I",str(root/"tests/ftp/ee"),"-I",str(root/"include"),
                    str(root/"src/ftp_session.c"),str(root/"src/dash_ftp.c"),str(root/"tests/ftp/test_session.c"),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True,timeout=10)
