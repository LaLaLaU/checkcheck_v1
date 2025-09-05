@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem Basic runtime environment tweaks
set "KMP_DUPLICATE_LIB_OK=TRUE"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "QT_FONT_DPI=96"
set "OMP_NUM_THREADS=1"
rem Force OCR to use local model folders under current directory
set "CHECKCHECK_OCR_MODELS=%CD%"

rem 1) Prefer bundled offline environment if present
if exist "delivery_offline\env\python.exe" (
    if exist "delivery_offline\env\Scripts\conda-unpack.exe" (
        if not exist "delivery_offline\env\.unpacked" (
            echo Fixing portable conda environment...
            delivery_offline\env\Scripts\conda-unpack.exe >nul 2>&1
            if %ERRORLEVEL% EQU 0 (
                echo ok>"delivery_offline\env\.unpacked"
            )
        )
    )
    echo Using offline Python environment...
    "delivery_offline\env\python.exe" src\main.py
    goto :end
)

rem 2) Else try conda environment 'checkcheck'
where conda >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    conda env list | findstr "checkcheck" >nul
    if %ERRORLEVEL% EQU 0 (
        echo Using conda environment 'checkcheck'...
        conda run -n checkcheck python src\main.py
        goto :end
    )
)

rem 3) Fallback to system Python
echo Using system Python...
python src\main.py

:end
pause

