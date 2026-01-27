@echo off
REM KiWay Extract Pins Plugin - Installation Script
REM For KiCAD 9.0 on Windows

echo ==========================================
echo  KiWay Extract Pins Plugin Installer
echo  Version 2.0.0
echo ==========================================
echo.

set "SOURCE=%~dp0extract_pins_plugin"
set "DEST=%USERPROFILE%\Documents\KiCad\9.0\scripting\plugins\extract_pins_plugin"

echo Source: %SOURCE%
echo Destination: %DEST%
echo.

if not exist "%SOURCE%" (
    echo ERROR: Source folder not found!
    echo Make sure you run this script from the plugin directory.
    pause
    exit /b 1
)

if exist "%DEST%" (
    echo Existing installation found. Removing...
    rmdir /s /q "%DEST%"
)

echo Copying plugin files...
xcopy /e /i /q "%SOURCE%" "%DEST%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ==========================================
    echo  Installation Complete!
    echo ==========================================
    echo.
    echo Next steps:
    echo   1. Open KiCAD PCB Editor
    echo   2. Go to Tools ^> External Plugins ^> Refresh Plugins
    echo   3. Find "Extract Component Pins with GUI" in the menu
    echo.
    echo For CLI usage:
    echo   python -m extract_pins_plugin --help
    echo.
) else (
    echo.
    echo ERROR: Installation failed!
)

pause
