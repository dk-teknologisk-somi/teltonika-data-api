@echo off
rem Builds dist\teltonika-data-api.exe. Run on Windows (double-click or from cmd/PowerShell).
setlocal
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" goto install

set "BASE_PYTHON="
where py >nul 2>&1 && set "BASE_PYTHON=py -3"
if not defined BASE_PYTHON where python >nul 2>&1 && set "BASE_PYTHON=python"
if not defined BASE_PYTHON (
    echo Python 3.11 or newer is required. Install it from https://www.python.org/downloads/
    goto fail
)
echo Creating virtual environment in %CD%\.venv...
%BASE_PYTHON% -m venv .venv || goto fail

:install
".venv\Scripts\python.exe" -m pip install -r requirements\build.txt || goto fail
".venv\Scripts\python.exe" -m PyInstaller packaging\teltonika-data-api.spec --noconfirm --clean || goto fail

echo.
echo Built: %CD%\dist\teltonika-data-api.exe
pause
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
