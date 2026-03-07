@echo off
setlocal
pushd "%~dp0"

chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo [probe] Run WM_HSCROLL probe with local env\python.exe ...
if not exist "env\python.exe" (
  echo [probe] ERROR: env\python.exe not found.
  echo [probe] Please run start_app.bat once to repair the environment.
  goto :end
)

rem Suggest running as Administrator (optional)
whoami /groups | find "S-1-16-12288" >nul
if %ERRORLEVEL% NEQ 0 (
  echo [probe] Hint: run as Administrator for full automation.
)

"env\python.exe" "tools\probe_hscroll.py" --title ".*(VJ-RT1|WH-VJ1000).*"
echo [probe] exit code: %ERRORLEVEL%

:end
popd
pause
