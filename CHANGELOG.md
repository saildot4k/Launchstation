# Launchstation changelog

## Rolling

- **Infinite list navigation wrap-around:** dashboard lists now cycle at boundaries (up from first selects last, down from last selects first), including File Browser views, app/library lists, Files/Devices pickers, Tools, Settings and HDD Manager.
- **R3Z file-copy behavior:** ordinary copies and overwrites now follow wLaunchELF_R3Z 4.80: remove the old destination, then create and write the requested file directly. This removes destination-stat and rename requirements that blocked memory-card pastes. Failed transfers retain Cut sources; overwritten files are not restored.
- **R3Z transfer settings:** restored device-specific copy buffers, eligible 1 MiB double buffering, 128/64 KiB IOP transfer-buffer tuning, native rename conflict probes. Two MMCE startup attempts per port and PSU/folder file-count progress remain. Close failures leave the output file for inspection.
- **Copy failure details:** compact stage/error, device, byte-count and build information make failed transfers diagnosable. A failed source-folder listing is no longer reported as an empty successful copy.
- **Cross-device copying:** positive short reads and writes complete the remaining bytes. Slot-2 card preparation happens before opening source files when leaving MX4SIO.
- **Clearer file operations:** the dashboard shows the filename, remaining megabytes and a progress bar while copying, with progress updates during deletion.
- **Release-page clarity:** the public release page now includes a concise Rolling changelog summary and links directly to full release notes and changelog history.
- **USB presentation and handoffs:** USB devices are named USB Mass Storage; browser paths display numbered `usbN:/` aliases. Ordinary ELF handoffs retain the fixed R3Z 4.80 `massN:/` policy.
- **Same-folder paste:** copying or moving back into the source directory is a harmless no-op rather than a false device failure.
- **PS2 clock:** the dashboard uses the hardware RTC. Manual date/time entry and Internet synchronization remain available; software-clock settings and saved checkpoints have been removed.
- **Storage loading:** returned mount waits redraw more frequently while retaining the existing device discovery windows. MMCE returns each probed port's bus state to the normal card/controller drivers.
- **Power-off:** setup starts only the power-off service, without loading unused DEV9 drivers, and detects failed initialization.

## Earlier changes

See the repository's merged pull requests for earlier development history.
