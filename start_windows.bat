@echo off
setlocal
cd /d "%~dp0"

set MACD_RUNTIME_MODE=windows

if exist windows_config.bat (
  call windows_config.bat
)

where py >nul 2>nul
if %errorlevel%==0 (
  set PY=py -3
) else (
  where python >nul 2>nul
  if %errorlevel% neq 0 (
    echo.
    echo [MACD] Python was not found.
    echo Please install Python 3.11 or newer, then run this file again.
    pause
    exit /b 1
  )
  set PY=python
)

if not exist .venv (
  echo [MACD] Creating local Python environment...
  %PY% -m venv .venv
  if %errorlevel% neq 0 (
    echo [MACD] Failed to create .venv
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate.bat

echo [MACD] Checking dependencies...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
if %errorlevel% neq 0 (
  echo [MACD] Dependency installation failed.
  pause
  exit /b 1
)

echo.
echo [MACD] Starting Windows calculation client...
echo Open http://127.0.0.1:8501 if the browser does not open automatically.
echo.

streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
pause
