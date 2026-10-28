@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto failed

echo Mercado AI Studio - Windows launcher
echo Please keep this window open.
where py >nul 2>nul
if errorlevel 1 goto use_python
set "STUDIO_PYTHON=py -3"
goto check_python

:use_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
set "STUDIO_PYTHON=python"

:check_python
%STUDIO_PYTHON% --version
if errorlevel 1 goto missing_python
if exist ".venv\Scripts\python.exe" goto install
%STUDIO_PYTHON% -m venv .venv
if errorlevel 1 goto failed

:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1
if errorlevel 1 goto failed
goto finished

:missing_python
echo Python was not found. Install Python 3.12 from python.org.
echo Enable "Add Python to PATH", then reopen this launcher.
goto failed

:failed
echo.
echo Startup failed. Please send a screenshot of this window.
pause
exit /b 1

:finished
echo Application stopped.
pause
exit /b 0
