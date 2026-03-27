@echo off
echo ============================================
echo  Icosele Vault - Windows Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Download Python 3.11+ from https://python.org/downloads/
    pause
    exit /b 1
)

:: Check Python version
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Found Python %PYVER%

:: Create virtual environment
echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

:: Activate and install
echo Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
if errorlevel 1 (
    echo ERROR: Failed to install requirements.
    pause
    exit /b 1
)

:: Create launcher
echo Creating launcher...
(
echo @echo off
echo cd /d "%%~dp0"
echo call .venv\Scripts\activate.bat
echo python main.py %%*
) > IcoseleVault.bat

:: Create data directory
if not exist data\vms mkdir data\vms

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo To start Icosele Vault, run: IcoseleVault.bat
echo.
echo IMPORTANT: You need QEMU for Windows installed.
echo Download from: https://qemu.weilnetz.de/w64/
echo.
echo For hardware acceleration, enable one of:
echo   - Hyper-V (Settings ^> Apps ^> Optional Features)
echo   - Windows Hypervisor Platform (same location)
echo.
pause
