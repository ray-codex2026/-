@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo 请先安装 Python 3.11 或 3.12，并勾选 Add Python to PATH。
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
if errorlevel 1 goto failed
exit /b 0
:failed
echo 启动失败。请检查上方错误、网络或 Python 版本。
pause
exit /b 1
