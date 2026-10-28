@echo off
setlocal
cd /d "%~dp0"
set "PY=C:\Users\H\miniforge3\envs\imglabel\python.exe"
if not exist "%PY%" set "PY=python"
netstat -ano | findstr /R /C:":5002 .*LISTENING" >nul
if not errorlevel 1 (
  echo Port 5002 is busy. No process will be stopped.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:5002
"%PY%" -B -c "import app; app.app.run(host='127.0.0.1', port=5002, debug=False)"
pause
