@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo   AES Secure File Transfer - Windows Launcher
echo ================================================
echo.

where python >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
    goto python_found
)
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py"
    goto python_found
)

echo ERROR: Python was not found on this computer.
echo Install Python from https://www.python.org/downloads/windows/
echo IMPORTANT: During installation, tick "Add python.exe to PATH".
echo Then close this window, open a NEW Command Prompt, and run this file again.
echo.
pause
exit /b 1

:python_found
echo Checking Python installation...
%PYTHON_CMD% --version
if errorlevel 1 goto failed

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto failed
)

echo Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto failed

echo Installing required packages...
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo Starting AES Secure File Transfer...
echo Open http://127.0.0.1:5000 in your browser.
echo Keep this window open while using the application.
echo Press Ctrl+C to stop the server.
echo.
python app.py
goto end

:failed
echo.
echo Setup failed. Check the error shown above.
echo If Python was just installed, restart Windows or open a new terminal.
pause
exit /b 1

:end
pause
