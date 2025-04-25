@echo off
echo Starting CheckCheck System with conda environment...

REM Check if conda is installed
where conda >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Conda is not installed or not in PATH.
    echo Please run install_env.bat first to set up the environment.
    pause
    exit /b 1
)

REM Set environment variable to allow duplicate OpenMP libraries
set KMP_DUPLICATE_LIB_OK=TRUE

REM Run the application using conda run command in the checkcheck environment
conda run -n checkcheck python src/main.py
if %ERRORLEVEL% NEQ 0 (
    echo Failed to run the application in conda environment.
    echo Please run install_env.bat first to set up the environment.
    pause
    exit /b 1
)

pause
