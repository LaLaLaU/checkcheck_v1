@echo off
setlocal
pushd "%~dp0"

rem Auto-elevate to administrator for UI automation (UIPI/UAC boundary).
whoami /groups | find "S-1-16-12288" >nul
if %ERRORLEVEL% NEQ 0 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  popd
  exit /b
)

if not exist "env\python.exe" (
  echo [demo] env\python.exe not found
  pause
  exit /b 1
)

rem Default char root to script\chars if not provided
if not defined CHECKCHECK_CHAR_ROOT (
  set "CHECKCHECK_CHAR_ROOT=%~dp0chars"
)

rem Strict match by code (no hardcoded file path)
set "DEMO_MAIN=J11B.5324.B.655.971"
echo [demo] FILE=%~f0
echo [demo] CHAR_ROOT=%CHECKCHECK_CHAR_ROOT%
echo [demo] MAIN_CODE=%DEMO_MAIN%

env\python.exe tools\demo_vendor_automation.py --title-re ".*VJ-RT1.1 Pro.*" --exe "C:\Users\video jet\Desktop\WH-VJ10001408.exe" --main "%DEMO_MAIN%" --grid-wait 0.3 --sleep-scale 0.4 --viewport-cols 124 --precise-insert --precise-comp 10 %*
set ERR=%ERRORLEVEL%
echo [demo] exit code: %ERR%
popd
pause
