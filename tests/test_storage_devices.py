"""Keep removed storage transports out of runtime, settings and both builds."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
paths = [*root.glob("src/*.[cS]"), *root.glob("include/*.h"),
         root / "igr/wle_igr.c", root / "Makefile", root / "embed.make",
         root / "ps2.yaml", root / "iop/oldlibs/ps2ftpd/src/FileSystem.c"]
for path in paths:
    assert not re.search(rb"ilink|ieee1394", path.read_bytes(), re.I), path

manifest = (root / "docs-site/manifest.json").read_text()
assert "ilink" not in manifest.lower()
assert not (root / "docs-site/content/ilink.html").exists()
print("PASS: storage removal covers drivers, builds, boot, browsing, settings, FTP, IGR and docs navigation")
