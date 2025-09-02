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

rem Force OCR to use local model folders under current directory
set CHECKCHECK_OCR_MODELS=%CD%

if exist env\Scripts\conda-unpack.exe env\Scripts\conda-unpack.exe

env\python.exe src\main.py

popd
pause
