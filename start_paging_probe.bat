@echo off
setlocal
pushd "%~dp0"

chcp 65001 >nul
echo [probe] Send WM_HSCROLL page/line to vendor grid (VSFlexGrid)
if not exist "env\python.exe" (
  echo [probe] env\python.exe not found. Run start_app.bat once.
  pause
  exit /b 1
)

rem You may change title regex or add %* to pass custom args
"env\python.exe" -X utf8 "tools\probe_paging.py" --title-re ".*VJ-RT1.1 Pro.*" --dir right --pages 1 --lines 0 %*
echo [probe] exit code: %ERRORLEVEL%
popd
pause

