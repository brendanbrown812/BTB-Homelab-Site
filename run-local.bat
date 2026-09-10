@echo off
setlocal
cd /d "%~dp0"
set "BTB_ROOT=%CD%"

echo.
echo ========================================
echo   BTB League - Local Development
echo ========================================
echo.

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example.
  echo.
  echo Add your Sleeper league ID and replace SECRET_KEY in .env,
  echo then run this file again.
  start "" notepad.exe "%BTB_ROOT%\.env"
  pause
  exit /b 1
)

findstr /C:"put-your-sleeper-league-id-here" ".env" >nul
if not errorlevel 1 (
  echo Your Sleeper league ID is still missing from .env.
  echo Update SLEEPER_LEAGUE_ID, save the file, and run this again.
  start "" notepad.exe "%BTB_ROOT%\.env"
  pause
  exit /b 1
)

findstr /C:"replace-with-at-least-32-random-bytes" ".env" >nul
if not errorlevel 1 (
  echo Replace the example SECRET_KEY in .env before starting BTB.
  start "" notepad.exe "%BTB_ROOT%\.env"
  pause
  exit /b 1
)

findstr /B /C:"BOOTSTRAP_ADMIN_PASSWORD=" ".env" >nul
if errorlevel 1 (
  echo.>> ".env"
  echo BOOTSTRAP_ADMIN_USERNAME=admin>> ".env"
  echo BOOTSTRAP_ADMIN_DISPLAY_NAME=Bootstrap Admin>> ".env"
  echo BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-temporary-admin-password>> ".env"
  echo Added the bootstrap admin settings to .env.
  echo Set BOOTSTRAP_ADMIN_PASSWORD, save the file, and run this again.
  start "" notepad.exe "%BTB_ROOT%\.env"
  pause
  exit /b 1
)

findstr /C:"BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-temporary-admin-password" ".env" >nul
if not errorlevel 1 (
  echo Set a temporary BOOTSTRAP_ADMIN_PASSWORD in .env before starting BTB.
  start "" notepad.exe "%BTB_ROOT%\.env"
  pause
  exit /b 1
)

powershell.exe -NoProfile -Command "$line = Get-Content -LiteralPath '.env' | Where-Object { $_ -like 'BOOTSTRAP_ADMIN_PASSWORD=*' } | Select-Object -First 1; if (-not $line -or (($line -split '=', 2)[1]).Length -lt 12) { exit 1 }"
if errorlevel 1 (
  echo BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters.
  echo Update it in .env, save the file, and run this again.
  start "" notepad.exe "%BTB_ROOT%\.env"
  pause
  exit /b 1
)

rem Local development always uses SQLite, even if .env contains server settings.
set "DATABASE_URL=sqlite+aiosqlite:///./btb-local.db"
set "LOCAL_CREATE_SCHEMA=true"

where py >nul 2>nul
if not errorlevel 1 (
  set "BTB_PYTHON=py"
  set "BTB_PYTHON_ARGS=-3"
) else (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "BTB_PYTHON=python"
    set "BTB_PYTHON_ARGS="
  ) else (
    if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
      set "BTB_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
      set "BTB_PYTHON_ARGS="
    ) else (
      echo Python 3 was not found. Install Python 3.12 or newer and try again.
      pause
      exit /b 1
    )
  )
)

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Install Node.js 22 or newer and try again.
  pause
  exit /b 1
)

if not exist "backend\.btb-venv\Scripts\python.exe" (
  echo Creating the backend Python environment...
  "%BTB_PYTHON%" %BTB_PYTHON_ARGS% -m venv "backend\.btb-venv"
  if errorlevel 1 goto :failed
)

if not exist "backend\.btb-venv\Scripts\uvicorn.exe" (
  echo Installing backend packages...
  "backend\.btb-venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
  if errorlevel 1 goto :failed
)

"backend\.btb-venv\Scripts\python.exe" -c "import tzdata" >nul 2>nul
if errorlevel 1 (
  echo Installing updated backend packages...
  "backend\.btb-venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
  if errorlevel 1 goto :failed
)

if not exist "node_modules\.bin\vinext.cmd" (
  echo Installing frontend packages...
  call npm ci --include=dev --include=optional
  if errorlevel 1 goto :failed
)

echo Starting BTB backend at http://localhost:8000 ...
start "BTB Backend" /D "%BTB_ROOT%\backend" cmd /k "node ..\scripts\run-with-log.mjs ..\logs\backend.log .btb-venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

echo Starting BTB frontend...
start "BTB Frontend" /D "%BTB_ROOT%" cmd /k "node scripts\run-with-log.mjs logs\frontend.log node scripts\run-framework.mjs dev"

echo.
echo Both services are starting in separate windows.
echo Frontend: http://localhost:5173
echo API docs: http://localhost:8000/docs
echo Logs: %BTB_ROOT%\logs
echo Close those two command windows to stop BTB.
echo.
timeout /t 3 >nul
start "" "http://localhost:5173/login"
exit /b 0

:failed
echo.
echo Local setup failed. Review the message above, then run this file again.
pause
exit /b 1
