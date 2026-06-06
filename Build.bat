@echo off
setlocal
cd /d "%~dp0"

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "NODE_DIR=%APPDATA%\fnm\aliases\default"

title AI PM Plan Task — Build Frontend

if not exist "%NODE_DIR%\node.exe" (
  echo  ERROR: Node.js not found at %NODE_DIR%
  echo  Please install Node via fnm: fnm install --lts
  pause & exit /b 1
)
if not exist "%ROOT%\frontend\node_modules" (
  echo  node_modules not found. Running npm install first...
  set HTTPS_PROXY=http://rb-proxy-apac.bosch.com:8080
  set HTTP_PROXY=http://rb-proxy-apac.bosch.com:8080
  "%NODE_DIR%\node.exe" "%NODE_DIR%\node_modules\npm\bin\npm-cli.js" --prefix "%ROOT%\frontend" install
)

echo.
echo  Building frontend (Vite + React) → html\standalone.html ...
echo.

"%NODE_DIR%\node.exe" "%NODE_DIR%\node_modules\npm\bin\npm-cli.js" --prefix "%ROOT%\frontend" run build

if errorlevel 1 (
  echo.
  echo  ERROR: Build failed. Check errors above.
  pause & exit /b 1
)

echo.
echo  ============================================================
echo   Build complete! html\standalone.html updated.
echo   Run Start.bat to serve it.
echo  ============================================================
echo.
pause
