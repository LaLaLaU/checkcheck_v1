@echo off
echo Packing conda environment for offline installation...

REM Check if conda is installed
where conda >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Conda is not installed or not in PATH.
    echo Please install Anaconda or Miniconda first.
    pause
    exit /b 1
)

REM Check if checkcheck environment exists
conda env list | findstr "checkcheck" >nul
if %ERRORLEVEL% NEQ 0 (
    echo Environment 'checkcheck' not found.
    echo Please run install_env.bat first to create the environment.
    pause
    exit /b 1
)

REM Install conda-pack if not already installed
echo Installing conda-pack...
call conda activate checkcheck
conda install -y -c conda-forge conda-pack
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install conda-pack.
    pause
    exit /b 1
)

REM Pack the environment
echo Packing environment 'checkcheck'...
conda pack -n checkcheck -o checkcheck_env.tar.gz
if %ERRORLEVEL% NEQ 0 (
    echo Failed to pack environment.
    pause
    exit /b 1
)

REM Create deployment package
echo Creating deployment package...
if not exist "dist" mkdir dist
copy checkcheck_env.tar.gz dist\
xcopy /E /I /Y src dist\src\
copy requirements.txt dist\
copy README.md dist\

REM Create installation script for client
echo Creating installation script for client...
(
echo @echo off
echo echo Extracting environment...
echo mkdir checkcheck_env
echo tar -xzf checkcheck_env.tar.gz -C checkcheck_env
echo echo Creating start script...
echo ^(
echo @echo off
echo call checkcheck_env\Scripts\activate.bat
echo python src\main.py
echo pause
echo ^) ^> start_app.bat
echo echo Installation complete!
echo echo Run start_app.bat to start the application.
echo pause
) > dist\install.bat

echo Deployment package created successfully in the 'dist' folder.
echo Please provide the entire 'dist' folder to the client.
pause
