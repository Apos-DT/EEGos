@echo off
setlocal EnableExtensions
rem ---------------------------------------------------------------------------
rem  EEG-EmoStudio one-click launcher (Windows). Double-click to start.
rem
rem  This file is ASCII-only on purpose: non-ASCII bytes in a .bat get mangled
rem  by the console code page and can corrupt the paths below. Every user-facing
rem  message (Chinese included) is printed by scripts\launch.py, which is UTF-8
rem  safe.
rem
rem  Discover only an interpreter here; dependency checks, port-conflict
rem  handling and opening the browser all live in scripts\launch.py so that
rem  Windows and Linux/macOS behave identically.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"

set "PYRUN="

rem 1) explicit override: set "EEG_PYTHON=C:\Path\To\python.exe"
if defined EEG_PYTHON set "PYRUN=%EEG_PYTHON%"
if defined PYRUN goto launch

rem 2) project virtual environment (fastest path once created)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1 && set "PYRUN=.venv\Scripts\python.exe"
)
if defined PYRUN goto launch

rem 3) py launcher: prefer 3.12 because the project is validated on it
py -3.12 -c "import sys" >nul 2>&1 && set "PYRUN=py -3.12"
if defined PYRUN goto launch
py -3 -c "import sys" >nul 2>&1 && set "PYRUN=py -3"
if defined PYRUN goto launch

rem 4) python on PATH
python -c "import sys" >nul 2>&1 && set "PYRUN=python"
if defined PYRUN goto launch

rem 5) default per-user install location (value keeps its own quotes because the
rem    user name may contain spaces; do not wrap it again at the call site)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PYRUN="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PYRUN goto launch

echo [error] No usable Python found.
echo         Install Python 3.12, or set the interpreter explicitly:
echo             set "EEG_PYTHON=C:\Path\To\python.exe"
echo             start.bat
echo.
pause
endlocal
exit /b 1

:launch
%PYRUN% "scripts\launch.py" %*
if errorlevel 1 (
  echo.
  echo [error] Startup failed - see the message above.
  pause
)
endlocal
exit /b 0
