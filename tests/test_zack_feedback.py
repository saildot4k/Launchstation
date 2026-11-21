from source_groups import component_source
from pathlib import Path
root=Path(__file__).resolve().parents[1]
hdr=(root/"include/dash_internal.h").read_text()
store=(root/"src/dash_store.c").read_text()
settings=component_source('src/dash_settings.c')
main=(root/"src/dash_main.c").read_text()
ui=(root/"src/dash_ui.c").read_text()
browser=(root/"src/dash_browser.c").read_text()
devices=(root/"src/dash_devices.c").read_text()
home=(root/"src/dash_home.c").read_text()

for field in ("home_shortcuts","icon_backing"):
    assert field in hdr
for key in ("Dash_HomeShortcuts","Dash_IconBacking"):
    assert key in store

assert "visible_sections[] = {DASH_SEC_HOME, DASH_SEC_FILES, DASH_SEC_TOOLS, DASH_SEC_SETTINGS}" in main
assert "section == DASH_SEC_FILES" in main and "dashFileBrowserTabClose();" in main
assert "DASH_SEC_APPS" in main  # older saved section values migrate to Home
assert "dashAdjacentSection(section, -1)" in main and "dashAdjacentSection(section, 1)" in main
assert "dashVisibleSectionCount()" in ui and "tab_w * vcount" in ui

assert "LastDir" in home
assert '"Applications"' in home and '"Last folder"' in home
assert "dashAppsScreen.input(in)" in home
assert "dashAppsScreen.draw()" in home
assert "dashRunMisc((const char *)setting + t->misc_offset);" in (root/"src/dash_tools.c").read_text()
assert "files_mode" not in hdr and "Dash_FilesMode" not in store
assert "&dashDevicesScreen" not in main
assert "const DashScreen dashFilesScreen" in (root/"src/dash_browser.c").read_text()
assert '"USB Mass Storage"' in devices
assert '"USB Mass Storage"' in (root/"src/dash_lib.c").read_text()
assert '"USB Storage"' not in (root/"src/dash_lib.c").read_text()
assert '"MASS (USB)"' not in devices
assert "usb%d:/" in devices  # keep path labels in device panels and picker
assert 'dashToast(DASH_TOAST_WARN, "Device not found");' in browser
assert "Not connected" in devices
assert "d->state == DASH_DEV_PROBE || d->state == DASH_DEV_ABSENT" in browser

assert "Panel transparency" in settings
assert "Control icon backings" in settings
assert "Home quick-launch shortcuts" in settings
assert "dashCfg.icon_backing" in ui and "dashCfg.icon_backing" in home
assert "dashCfg.home_shortcuts" in home
print("zack structural feedback contract: OK")

clock = (root / "src/dash_clock_sync.c").read_text()
init = (root / "src/init.c").read_text()
yaml = (root / "ps2.yaml").read_text()
make = (root / "Makefile").read_text()

assert '"Set PS2 Clock"' in settings
assert "dashClockSetManual" in settings
assert '"Sync from Internet"' in settings
assert "dashClockSyncInternet" in settings
assert 'static const char server[] = "0.pool.ntp.org";' in clock
assert "SNTP_AGREEMENT" not in clock and "sources disagree" not in clock
assert "sceCdWriteClock" in clock and "sceCdReadClock" in clock
assert "9ULL * 3600ULL" in clock
assert "toBcd" in clock
assert "ensureDashboardIpNetworkReady" in init
assert "src/dash_clock_sync.c" in yaml
assert "ps2ips, cglue" in yaml
assert "dash_clock_sync.o" in make
print("clock sync contract: OK")
