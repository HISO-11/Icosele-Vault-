@echo off
echo ============================================
echo  Icosele Vault — Windows EXE Build
echo ============================================
echo.

cd /d "%~dp0\.."

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Activate venv if it exists, otherwise create one
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt -q
)

:: Install PyInstaller if not present
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller -q
)

echo.
echo Building IcoseleVault.exe...
echo.

pyinstaller --onefile --windowed ^
    --name "IcoseleVault" ^
    --icon assets\icon.png ^
    --add-data "assets;assets" ^
    --add-data "data;data" ^
    --add-data "config;config" ^
    --add-data "plugins;plugins" ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtWidgets ^
    --hidden-import PySide6.QtNetwork ^
    --hidden-import app.platform_utils ^
    --hidden-import app.audit_log ^
    --hidden-import app.snapshot_store ^
    --hidden-import app.webhook_manager ^
    --hidden-import app.plugin_manager ^
    --hidden-import app.ollama_client ^
    --hidden-import app.host_monitor ^
    --hidden-import app.web_console ^
    --hidden-import app.auth_manager ^
    --hidden-import app.replication_manager ^
    --hidden-import app.compliance_reports ^
    --hidden-import app.usb_monitor ^
    main.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo ============================================
echo.
echo Output: dist\IcoseleVault.exe
echo.
pause
