@echo off
chcp 65001 >nul
echo Starting CheckCheck in conda environment 'checkcheck'...

where conda >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Conda is not installed or not in PATH.
    echo Please run install_env.bat first to set up the environment.
    pause
    exit /b 1
)

set "KMP_DUPLICATE_LIB_OK=TRUE"
set "PYTHONUTF8=1"
set "QT_FONT_DPI=96"
set "OMP_NUM_THREADS=1"

rem Force OCR to use local model folders under current directory
set "CHECKCHECK_OCR_MODELS=%CD%"

conda run -n checkcheck python src/main.py
if %ERRORLEVEL% NEQ 0 (
    echo Failed to run the application in conda environment.
    echo Please run install_env.bat first to set up the environment.
    pause
    exit /b 1
)

pause
