@echo off
setlocal
pushd %~dp0

rem Ensure UTF-8 console/output
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem Runtime tweaks
set KMP_DUPLICATE_LIB_OK=TRUE
set QT_FONT_DPI=96
set "XDG_CACHE_HOME=%CD%\\.cache"
set "PADDLE_HOME=%CD%\\.cache\\paddle"
if not exist "%XDG_CACHE_HOME%" mkdir "%XDG_CACHE_HOME%" >nul 2>&1
if not exist "%PADDLE_HOME%" mkdir "%PADDLE_HOME%" >nul 2>&1

rem Force OCR to use local model folders under current directory
set CHECKCHECK_OCR_MODELS=%CD%

if exist env\Scripts\conda-unpack.exe (
    if not exist env\.unpacked (
        env\Scripts\conda-unpack.exe >nul 2>&1
        if %ERRORLEVEL% EQU 0 (
            echo ok>env\.unpacked
        )
    )
)

env\python.exe src\main.py

popd
pause
