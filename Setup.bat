@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
title AI PM Plan Task - Setup

echo.
echo  ============================================================
echo   AI PM Plan Task - First-Time Setup
echo  ============================================================
echo.

REM Check if .venv already exists and works
if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -c "import fastapi, uvicorn" >nul 2>&1
  if not errorlevel 1 (
    echo  .venv already exists and working - nothing to do.
    echo  Run Start.bat to launch the app.
    echo.
    pause
    exit /b 0
  )
)

echo  Setting up Python environment...
echo.

REM Source venv path (absolute - from AI_PM_Assisstant_Final which is in same Project_code folder)
set "SRC=C:\Users\GDN4HC\OneDrive - Bosch Group\1. Project\Project_code\AI_PM_Assisstant_Final\.venv"

if exist "%SRC%\Scripts\python.exe" (
  echo  Copying Python environment from AI_PM_Assisstant_Final...
  echo  This will take 2-5 minutes. Please wait...
  echo.
  xcopy "%SRC%\" "%ROOT%\.venv\" /E /I /H /Y /Q
  if errorlevel 1 (
    echo  ERROR: Copy failed.
    pause & exit /b 1
  )
  echo  Copy done. Verifying...
  "%ROOT%\.venv\Scripts\python.exe" -c "import fastapi, uvicorn, pydantic, requests, slowapi, openpyxl" >nul 2>&1
  if not errorlevel 1 (
    echo  All packages OK.
    goto done
  )
  echo  Installing missing packages...
  set HTTPS_PROXY=http://rb-proxy-apac.bosch.com:8080
  set HTTP_PROXY=http://rb-proxy-apac.bosch.com:8080
  "%ROOT%\.venv\Scripts\python.exe" -m pip install -r "%ROOT%\requirements.txt" --proxy http://rb-proxy-apac.bosch.com:8080 -q
  goto done
)

REM Try Python on PATH as last resort
where python >nul 2>&1
if not errorlevel 1 (
  echo  Found Python on PATH. Creating fresh environment...
  python -m venv "%ROOT%\.venv"
  if errorlevel 1 ( echo  ERROR: venv failed. & pause & exit /b 1 )
  set HTTPS_PROXY=http://rb-proxy-apac.bosch.com:8080
  set HTTP_PROXY=http://rb-proxy-apac.bosch.com:8080
  "%ROOT%\.venv\Scripts\python.exe" -m pip install -r "%ROOT%\requirements.txt" --proxy http://rb-proxy-apac.bosch.com:8080
  goto done
)

echo  ERROR: Cannot find Python or AI_PM_Assisstant_Final\.venv
echo.
echo  Please check:
echo    "%SRC%"
echo  exists and contains Scripts\python.exe
echo.
pause
exit /b 1

:done
echo.

REM ── Frontend npm install ───────────────────────────────────────────────────────
set "NODE_DIR=%APPDATA%\fnm\aliases\default"
if exist "%NODE_DIR%\node.exe" (
  if not exist "%ROOT%\frontend\node_modules" (
    echo  Installing frontend dependencies (npm install)...
    set HTTPS_PROXY=http://rb-proxy-apac.bosch.com:8080
    set HTTP_PROXY=http://rb-proxy-apac.bosch.com:8080
    "%NODE_DIR%\node.exe" "%NODE_DIR%\node_modules\npm\bin\npm-cli.js" --prefix "%ROOT%\frontend" install
    if errorlevel 1 (
      echo  WARNING: npm install failed. Dev.bat may not work until you run npm install manually in frontend/.
    ) else (
      echo  Frontend dependencies installed OK.
    )
  ) else (
    echo  Frontend node_modules already exists - skipping npm install.
  )
) else (
  echo  NOTE: Node.js ^(fnm^) not found — skipping frontend npm install.
  echo  To enable hot-reload dev mode, install Node via fnm and run:
  echo    cd frontend ^&^& npm install
)

echo.
echo  ============================================================
echo   Setup complete!
echo   - Run Start.bat   to serve production build  ^(port 8080^)
echo   - Run Dev.bat     to run hot-reload dev mode ^(port 5173^)
echo   - Run Build.bat   to rebuild frontend only
echo  ============================================================
echo.
pause
