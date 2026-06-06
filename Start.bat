@echo off
setlocal
cd /d "%~dp0"

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\.venv\Scripts\python.exe"
set "BPORT=8000"
set "PORT=8080"
set "HTML_DIR=%ROOT%\html"

title AI PM Plan Task — Super OPL

REM ── Check .venv ───────────────────────────────────────────────────────────────
if not exist "%VENV%" (
  echo.
  echo  ERROR: .venv not found.
  echo  Please run Setup.bat first.
  echo.
  pause & exit /b 1
)

REM ── Kill old processes on both ports ─────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%BPORT% "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%PORT% "') do taskkill /F /PID %%a >nul 2>&1

echo.
echo  ============================================================
echo   AI PM Plan Task — Super OPL Standalone
echo  ============================================================
echo   Backend  : http://127.0.0.1:%BPORT%
echo   App      : http://localhost:%PORT%/standalone.html
echo  ============================================================
echo.
echo  Starting backend...

REM ── Write launcher (avoid nested-quote issue) ─────────────────────────────────
set "LAUNCHER=%TEMP%\opl_backend_launcher.bat"
echo @echo off > "%LAUNCHER%"
echo cd /d "%ROOT%" >> "%LAUNCHER%"
echo "%VENV%" -m uvicorn backend.main:app --host 127.0.0.1 --port %BPORT% >> "%LAUNCHER%"

start "OPL-Backend" /min "%LAUNCHER%"

REM ── Wait for backend (up to 20s) ─────────────────────────────────────────────
set /a n=0
:chk
set /a n+=1
if %n% gtr 20 ( echo  Backend timeout — opening anyway... & goto open )
timeout /t 1 /nobreak >nul
%SystemRoot%\System32\curl.exe -s -f http://127.0.0.1:%BPORT%/api/health >nul 2>&1
if errorlevel 1 goto chk
echo  Backend ready ^(took %n%s^).

:open
REM ── Start HTTP server for HTML ────────────────────────────────────────────────
start "OPL-HTTP" /b "%VENV%" -m http.server %PORT% --directory "%HTML_DIR%" --bind 127.0.0.1
timeout /t 1 /nobreak >nul

REM ── Open browser ─────────────────────────────────────────────────────────────
start "" "http://localhost:%PORT%/standalone.html"
echo  Opened browser.
echo.
echo  Press any key to STOP all servers.
pause >nul

REM ── Cleanup ───────────────────────────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%PORT% "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%BPORT% "') do taskkill /F /PID %%a >nul 2>&1
del "%LAUNCHER%" >nul 2>&1
echo  Stopped.
