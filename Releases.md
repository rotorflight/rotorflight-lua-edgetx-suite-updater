# 1.0.1

- Radio detection: a drive is only treated as an EdgeTX radio with a firmware marker (`RADIO/radio.yml`, `RADIO/radio.bin` or a `.cpuid` file), or with `SCRIPTS` plus three standard EdgeTX folders. A bare `SCRIPTS` folder such as `C:\SCRIPTS` is no longer selected as the install target. When no radio is found, no drive is preselected.
- Source-branch installs (for example `Branch: master`): language files containing `--` inside a string (such as `steht dort --.`) are read correctly. Before, every `@i18n(...)@` tag stayed unresolved and the menus showed raw keys.
- A language file that cannot be read now stops the installation with an error message instead of silently installing without translations.

# 1.0.0

- Initial standalone release, split out of rotorflight-lua-edgetx-suite's `bin/updater` tool.
- Desktop utility (Windows/macOS/Linux) to detect connected EdgeTX radios/SD cards and install or update the Rotorflight Lua EdgeTX Suite from GitHub releases, pre-releases, or local ZIP files.
