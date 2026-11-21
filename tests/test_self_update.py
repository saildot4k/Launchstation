"""Guard the native staged updater and release-integrity contract."""
from source_groups import component_source
from pathlib import Path

root = Path(__file__).resolve().parents[1]
http_h = (root / "include/https_client.h").read_text()
http_c = (root / "src/https_client.c").read_text()
update = (root / "src/self_update.c").read_text()
tools = (root / "src/dash_tools.c").read_text()
settings = component_source('src/dash_settings.c')
yaml = (root / "ps2.yaml").read_text()
workflow = (root / ".github/workflows/compile.yml").read_text()

assert "httpsDownloadFd" in http_h
assert "httpsDownloadFd" in http_c
assert "Too many HTTPS redirects" in http_c
assert "mbedtls_sha256_update" in http_c
assert "max_bytes" in http_c
assert "Transfer-Encoding" in http_c and "chunked" in http_c

assert "r3LaunchELF_ATTDASH.ELF.sha256" not in update
assert "parse_expected_sha" in update
assert "SELF_UPDATE_ASSET" in update
assert "selfUpdateExtractPsu(package, stage, package_size)" in update
assert 'filerCaptureSasTimestamp(parent, &sas_timestamp)' in update
assert 'filerRestoreSasTimestamp(parent, &sas_timestamp)' in update
assert "wleExists(package) || wleExists(stage)" in update
assert update.index("wleExists(package) || wleExists(stage)") < update.index("download_file(UPDATE_ELF_URL")
assert "checkELFheader(stage)" in update
assert '"%s.UPDATE"' in update
assert "memcmp(expected, actual" in update
assert "supported_boot_path" in update

assert '#include "self_update.h"' in tools
assert "releaseAssetDigest" in tools
assert '"digest"' in tools
assert "selfUpdateInstall(ca_path, asset_digest" in tools
assert '"Install update"' in tools
assert "SHA-256 verified and installed in place" in tools

assert "src/self_update.c" in yaml
assert "sha256sum Launchstation.ELF > Launchstation.ELF.sha256" not in workflow
assert "artifacts/Launchstation.ELF.sha256#SHA-256" not in workflow
assert "scripts/package_apps.py" in workflow

print("PASS: native updater verifies GitHub release digests, checks space, verifies and replaces without backups")

update_ca = (root / "res/WLE-UPDATE-CA.PEM").read_text()
assert update_ca.count("-----BEGIN CERTIFICATE-----") >= 2

# Controller variants select matching package and ELF names.
header = (root / "include/self_update.h").read_text()
assert '#ifdef DS34' in header
assert '"APP_LAUNCHSTATION-DS"' in header and '"APP_LAUNCHSTATION"' in header
assert '"LAUNCHSTATION-DS.ELF"' in header and '"LAUNCHSTATION.ELF"' in header
assert 'releaseAssetDigest(response.body, SELF_UPDATE_ASSET' in tools

assert '.BAK' not in update
assert 'UPDATE_SPACE_MARGIN (100 * 1024)' in update
assert 'reserve_update_space(reserve)' in update
assert 'free_bytes < (u64)package_size' in update
assert 'dashWorkerSubmit(title, 0,' in tools

for name in ("title.cfg", "WLE-UPDATE-CA.PEM", "BGM.ADP", "icon.sys", "list.icn", "copy.icn", "del.icn", "APPINFO.PBT"):
    assert f'"{name}"' in update
assert "selfUpdateExtractPsuAppInfo" in update
assert "publish_update_file" in update and "DashStorageProgress" in update
assert "updateDownloadProgress" in update and "updateCopyProgress" in update
assert update.index("selfUpdateExtractPsuAppInfo(package") < update.index("publish_update_file(parent, update_asset_name(i)")
