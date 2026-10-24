"""Driver auto-start is removed; SELECT recovery boot still skips saved settings."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
modules = (root / "src/main_modules.c").read_text()
store = (root / "src/dash_store.c").read_text()
devices = (root / "src/dash_devices.c").read_text()
settings = (root / "src/dash_settings.c").read_text()
main = (root / "src/dash_main.c").read_text()
header = (root / "include/dash_internal.h").read_text()

assert "new_pad & PAD_SELECT" in modules
assert "boot_show_all_devices = 1;" in modules
assert "boot_safe_mode = 1;" in modules
safe = store[store.index("void dashStoreInit(void)"):store.index("int dashStoreLoaded(void)")]
assert safe.index("if (!boot_safe_mode)") < safe.index("dashKvParse(text, settingsKv, &scan_reset);")
for source in (store, devices, settings, main, header):
    for obsolete in ("dev_auto", "DASH_DEVA_", "S_DEVA_", "P_AUTOSTART", "Dash_DevAuto",
                     "dashDevicesAuto", "dashBootDeviceBit", "autoprobe_pending",
                     "show_unavailable_devices", "S_SHOW_UNAVAILABLE", "Dash_ShowUnavailableDevices"):
        assert obsolete not in source, obsolete
assert "void dashDevicesStartForPath(" in devices
assert "int dashDevicesStart(" in devices
print("PASS: driver auto-start UI/config/startup/restart removed; on-demand loading and SELECT safe mode retained")
