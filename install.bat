@echo off
REM Dataport AI for Tableau -- one-time installer for Windows.
REM
REM Double-click this file (or run it from cmd / PowerShell) to install.
REM It will create a double-clickable launcher when finished.

setlocal enableextensions
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================================
echo  Dataport AI for Tableau -- Setup
echo ============================================================
echo  This installer will:
echo    1. Check that Python 3.10+ is available
echo    2. Create an isolated Python environment in .\.venv
echo    3. Install the dependencies (about 200MB, 1-2 minutes)
echo    4. Create a double-clickable launcher: 'Dataport AI.bat'
echo.
echo  You only need to run this once.
echo ------------------------------------------------------------
echo.

REM --- Python check ---------------------------------------------

where python >nul 2>&1
if errorlevel 1 (
    echo X Python not found.
    echo.
    echo   Install Python 3.11 or 3.12 from https://python.org/downloads
    echo   IMPORTANT: tick "Add Python to PATH" during installation.
    echo   Then run this installer again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo Python %PY_VER% detected

REM Verify >= 3.10
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo X Python %PY_VER% is too old. Need 3.10 or newer.
    echo   Install from https://python.org/downloads
    pause
    exit /b 1
)

REM --- venv -----------------------------------------------------

if not exist ".venv" (
    echo - Creating Python environment in .venv\ ...
    python -m venv .venv
    if errorlevel 1 (
        echo X Failed to create virtual environment.
        pause
        exit /b 1
    )
)
echo + Virtual environment ready

REM --- install deps ---------------------------------------------

echo - Installing dependencies (this takes a minute) ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\pip.exe" install --quiet -e .
if errorlevel 1 (
    echo X Dependency installation failed.
    echo   Run the following to see the full error:
    echo     .venv\Scripts\pip.exe install -e .
    pause
    exit /b 1
)
echo + Dependencies installed

REM --- create launcher ------------------------------------------

set "LAUNCHER=Dataport AI.bat"

(
  echo @echo off
  echo REM Double-click me to launch the Dataport AI for Tableau.
  echo chcp 65001 ^>nul
  echo cd /d "%%~dp0"
  echo if not exist ".venv" ^(
  echo   echo First-time setup wasn't completed. Run install.bat first.
  echo   pause
  echo   exit /b 1
  echo ^)
  echo cls
  echo ".venv\Scripts\python.exe" -m src.tui
  echo if errorlevel 1 ^(
  echo   echo.
  echo   echo The app exited with an error.
  echo   pause
  echo ^)
) > "%LAUNCHER%"

echo + Created '%LAUNCHER%' (double-click to launch)

REM --- done -----------------------------------------------------

echo.
echo ============================================================
echo  All set!
echo ============================================================
echo.
echo  Next steps:
echo.
echo    1. Get an Anthropic API key
echo       https://console.anthropic.com/settings/keys
echo       (sign up, then "Create Key". Dataport AI uses this
echo        to generate data stories from your spreadsheets.)
echo.
echo    2. Launch the app
echo       Double-click 'Dataport AI.bat' in this folder.
echo.
echo    3. Optional: drop CSV/Excel files into the 'samples' folder
echo       so they show up easily in the file picker.
echo.
echo ============================================================
echo.
pause
