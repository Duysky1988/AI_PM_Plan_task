@echo off
setlocal
cd /d "%~dp0"

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\.venv\Scripts\python.exe"
set "NODE_DIR=%APPDATA%\fnm\aliases\default"
set "BPORT=8000"
set "FE_PORT=5173"

title AI PM Plan Task — Dev Mode

REM ── Checks ────────────────────────────────────────────────────────────────────
if not exist "%VENV%" (
  echo  ERROR: .venv not found. Run Setup.bat first.
  pause & exit /b 1
)
if not exist "%NODE_DIR%\node.exe" (
  echo  ERROR: Node.js not found at %NODE_DIR%
  echo  Please run: fnm install --lts
  pause & exit /b 1
)
if not exist "%ROOT%\frontend\node_modules" (
  echo  ERROR: frontend/node_modules not found.
  echo  Run Setup.bat first to install npm dependencies.
  pause & exit /b 1
)

REM ── Kill old processes ────────────────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%BPORT% "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%FE_PORT% "') do taskkill /F /PID %%a >nul 2>&1

echo.
echo  ============================================================
echo   AI PM Plan Task — Dev Mode
echo  ============================================================
echo   Backend  : http://127.0.0.1:%BPORT%  (FastAPI + auto-reload)
echo   Frontend : http://localhost:%FE_PORT%  (Vite hot-reload)
echo  ============================================================
echo.

REM ── Backend (with --reload for dev) ──────────────────────────────────────────
set "BACKEND_LAUNCHER=%TEMP%\opl_backend_dev.bat"
echo @echo off > "%BACKEND_LAUNCHER%"
echo cd /d "%ROOT%" >> "%BACKEND_LAUNCHER%"
echo "%VENV%" -m uvicorn backend.main:app --host 127.0.0.1 --port %BPORT% --reload >> "%BACKEND_LAUNCHER%"
start "OPL-Backend-Dev" "%BACKEND_LAUNCHER%"

REM ── Wait for backend (up to 15s) ─────────────────────────────────────────────
set /a n=0
:chk
set /a n+=1
if %n% gtr 15 ( echo  Backend timeout — starting frontend anyway... & goto fe )
timeout /t 1 /nobreak >nul
%SystemRoot%\System32\curl.exe -s -f http://127.0.0.1:%BPORT%/api/health >nul 2>&1
if errorlevel 1 goto chk
echo  Backend ready (took %n%s).

:fe
REM ── Vite dev server ───────────────────────────────────────────────────────────
set "VITE_LAUNCHER=%TEMP%\opl_vite_dev.bat"
echo @echo off > "%VITE_LAUNCHER%"
echo cd /d "%ROOT%\frontend" >> "%VITE_LAUNCHER%"
echo "%NODE_DIR%\node.exe" "%NODE_DIR%\node_modules\npm\bin\npm-cli.js" run dev >> "%VITE_LAUNCHER%"
start "OPL-Vite-Dev" "%VITE_LAUNCHER%"

timeout /t 2 /nobreak >nul
start "" "http://localhost:%FE_PORT%"

echo  Vite dev server starting at http://localhost:%FE_PORT%
echo  (Changes to frontend/src/ hot-reload automatically)
echo.
echo  Press any key to STOP all servers.
pause >nul

REM ── Cleanup ───────────────────────────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%BPORT% "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%FE_PORT% "') do taskkill /F /PID %%a >nul 2>&1
del "%BACKEND_LAUNCHER%" >nul 2>&1
del "%VITE_LAUNCHER%" >nul 2>&1
echo  Stopped.
