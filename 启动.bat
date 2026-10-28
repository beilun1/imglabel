@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动人机协同图像标注系统...
echo 浏览器打开: http://127.0.0.1:5000
set "PY=C:\Users\H\miniforge3\envs\imglabel\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" app.py
pause
