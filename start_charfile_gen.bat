@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

if not exist "env\python.exe" (
  echo [error] env\python.exe not found.
  pause
  exit /b 1
)

env\python.exe tools\charfile_gen\gui.py
if errorlevel 1 (
  echo [error] charfile generator exited with error.
  pause
  exit /b 1
)

endlocal
