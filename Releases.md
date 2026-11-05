# 1.0.3

- (in progress)

# 1.0.2

- Support for the suite's new `SCRIPTS/RFSUITE` layout: code goes to `SCRIPTS/RFSUITE/core`, pilot data to `SCRIPTS/RFSUITE/user`. A source-branch install stages the layout the tree's own `lib/paths.lua` names, so older and newer branches keep working. An install removes the code of every layout plus the bytecode the radio wrote beside the entry files (which can point at a removed folder); the data folders are never touched.
- The installed code version shown in the updater now reflects the code the entry file actually loads, even when both code folders are present on a card (e.g. after an older archive was unpacked over a newer install).
- An install now stops when a folder cannot be removed, instead of merging new files into a partly removed one.
- The settings backup step and its checkbox have been dropped: the suite writes `preferences.lua` and converts a `preferences.ini` itself, and an install no longer removes the data folder, so the step protected nothing.

# 1.0.1

- Radio detection: a drive is only treated as an EdgeTX radio with a firmware marker (`RADIO/radio.yml`, `RADIO/radio.bin` or a `.cpuid` file), or with `SCRIPTS` plus three standard EdgeTX folders. A bare `SCRIPTS` folder such as `C:\SCRIPTS` is no longer selected as the install target. When no radio is found, no drive is preselected.
- Source-branch installs (for example `Branch: master`): language files containing `--` inside a string (such as `steht dort --.`) are read correctly. Before, every `@i18n(...)@` tag stayed unresolved and the menus showed raw keys.
- A language file that cannot be read now stops the installation with an error message instead of silently installing without translations.

# 1.0.0

- Initial standalone release, split out of rotorflight-lua-edgetx-suite's `bin/updater` tool.
- Desktop utility (Windows/macOS/Linux) to detect connected EdgeTX radios/SD cards and install or update the Rotorflight Lua EdgeTX Suite from GitHub releases, pre-releases, or local ZIP files.
