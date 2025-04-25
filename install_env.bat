@echo off
echo Creating Python 3.8 environment for CheckCheck...

REM Check if conda is installed
where conda >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Conda is not installed or not in PATH.
    echo Please install Anaconda or Miniconda from https://www.anaconda.com/products/distribution
    echo or https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

REM Configure conda to use mirrors in China
echo Configuring conda to use mirrors in China...
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes
conda config --set ssl_verify false
if %ERRORLEVEL% NEQ 0 (
    echo Warning: Failed to configure conda mirrors. Installation might be slower.
)

REM Remove default channels to force using only tsinghua mirrors
echo Removing default channels to ensure using only mirrors...
conda config --remove channels defaults
if %ERRORLEVEL% NEQ 0 (
    echo Warning: Failed to remove default channels.
)

REM Create conda environment with Python 3.8
echo Creating conda environment with Python 3.8...
conda create -y -n checkcheck python=3.8
if %ERRORLEVEL% NEQ 0 (
    echo Failed to create conda environment.
    pause
    exit /b 1
)

REM Activate conda environment and install dependencies
echo Activating conda environment and installing dependencies...
call conda activate checkcheck
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate conda environment.
    pause
    exit /b 1
)

REM Install dependencies using pip with Tsinghua mirror
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies.
    echo Please check your internet connection and try again.
    pause
    exit /b 1
)

echo Environment setup completed successfully!
echo To start the application, run start_with_conda.bat
pause
