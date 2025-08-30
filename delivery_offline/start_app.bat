@echo off
setlocal
pushd %~dp0
set KMP_DUPLICATE_LIB_OK=TRUE
set PYTHONUTF8=1
set QT_FONT_DPI=96

if exist env\Scripts\conda-unpack.exe env\Scripts\conda-unpack.exe

env\python.exe src\main.py

popd
pause
