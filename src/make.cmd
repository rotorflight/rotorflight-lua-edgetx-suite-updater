@echo off
setlocal
cd /d %~dp0

if not defined UPDATER_VERSION set UPDATER_VERSION=1.0.0

echo [1/6] Checking for pyinstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install -r requirements_updater.txt || goto :error
)

echo [2/6] Generating version info (%UPDATER_VERSION%)...
python gen_version_info.py || goto :error

echo [3/6] Compiling updater.py to standalone EXE...
python -m PyInstaller --onefile --noupx updater.py --name rotorflight-lua-edgetx-suite-updater --windowed --version-file version_info.txt --icon icon.ico || goto :error

echo [4/6] Moving rotorflight-lua-edgetx-suite-updater.exe into parent folder...
taskkill /f /im rotorflight-lua-edgetx-suite-updater.exe >nul 2>&1
if exist ..\rotorflight-lua-edgetx-suite-updater.exe (
    del /f /q ..\rotorflight-lua-edgetx-suite-updater.exe >nul 2>&1
)
move /Y dist\rotorflight-lua-edgetx-suite-updater.exe ..\rotorflight-lua-edgetx-suite-updater.exe >nul

echo [5/6] Cleaning up build tree...
rd /s /q build
rd /s /q dist
del /q rotorflight-lua-edgetx-suite-updater.spec

echo [6/6] Build complete. rotorflight-lua-edgetx-suite-updater.exe is ready at: ..\rotorflight-lua-edgetx-suite-updater.exe
goto :eof

:error
echo Build failed.
exit /b 1
