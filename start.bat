@echo off
rem EEG-EmoStudio launcher (Windows). ASCII only on purpose: non-ASCII in .bat
rem can be garbled by the console codepage and break paths.
cd /d "%~dp0"

if "%EEG_WEB_HOST%"=="" set "EEG_WEB_HOST=0.0.0.0"
if "%EEG_WEB_PORT%"=="" set "EEG_WEB_PORT=8770"
if "%EEG_WEB_TOKEN%"=="" echo [warn] EEG_WEB_TOKEN not set: admin pages are visible to the whole LAN.

if defined EEG_PYTHON goto run

rem Prefer the 3.12 interpreter that has fastapi/torch installed.
py -3.12 -c "import fastapi" >nul 2>&1
if not errorlevel 1 (
  set "EEG_PYTHON=py -3.12"
  goto run
)

python -c "import fastapi" >nul 2>&1
if not errorlevel 1 (
  set "EEG_PYTHON=python"
  goto run
)

echo [error] No Python with fastapi found.
echo         Set EEG_PYTHON to the full path of your Python 3.12 interpreter, e.g.
echo         set "EEG_PYTHON=C:\Path\To\python.exe"
pause
exit /b 1

:run
echo Interpreter: %EEG_PYTHON%
%EEG_PYTHON% -m webapp
