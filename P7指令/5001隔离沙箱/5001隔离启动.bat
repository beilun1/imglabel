@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem ============================================================
rem  5001 隔离沙箱：在 %TEMP%\isolated_5001 起一份项目副本
rem  用法：5001隔离启动.bat [demo-展示 或 demo-预标注]，缺省 demo-预标注
rem  真实 data weights dataset 只读；不改 app.py 端口；不结束任何进程
rem  本文件为 GBK(936) 编码、不用 chcp 65001：cmd 按 UTF-8 读批处理时中文会错位成乱码命令，勿另存为 UTF-8
rem ============================================================
set "GALLERY_N=20"
set "PRELABEL_N=8"
set "PORT=5001"
set "PY=C:\Users\H\miniforge3\envs\imglabel\python.exe"
for %%I in ("%~dp0..\..") do set "SRC=%%~fI"
set "DST=%TEMP%\isolated_5001"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=demo-预标注"
set "KEY="
if /i "%MODE%"=="demo-展示" set "KEY=show"
if /i "%MODE%"=="demo-show" set "KEY=show"
if /i "%MODE%"=="demo-预标注" set "KEY=prelabel"
if /i "%MODE%"=="demo-prelabel" set "KEY=prelabel"
if not defined KEY goto :bad_mode
if "%KEY%"=="show" set "MODE=demo-展示"
if "%KEY%"=="show" set "N=%GALLERY_N%"
if "%KEY%"=="prelabel" set "MODE=demo-预标注"
if "%KEY%"=="prelabel" set "N=%PRELABEL_N%"

echo ============================================================
echo  5001 隔离沙箱 · 模式：%MODE%
echo  真实项目：%SRC%
echo  副本目录：%DST%
echo ============================================================
if not exist "%SRC%\app.py" goto :no_src
if not exist "%PY%" goto :no_py

rem 先查端口：若上次的副本服务还开着，重建副本会把它正在用的文件换掉
echo [1/5] 检测端口 %PORT% 占用...
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 goto :port_busy
echo       端口 %PORT% 空闲

echo [2/5] 复制项目代码（排除 weights data dataset runs __pycache__ .git .workbuddy）...
robocopy "%SRC%" "%DST%" /MIR /XD weights data dataset runs __pycache__ .git .workbuddy /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :copy_fail

echo [3/5] 按模式重建副本 data ...
if exist "%DST%\data" rd /s /q "%DST%\data"
mkdir "%DST%\data\curated\images" "%DST%\data\annotations" "%DST%\data\records"
set /a CNT=0, JCNT=0
for /f "delims=" %%F in ('dir /b /a-d /on "%SRC%\data\curated\images" ^| findstr /i /r "\.jpg$ \.jpeg$ \.png$"') do call :take "%%F"
echo       已拷图片 %CNT% 张（按文件名顺序取前 %N% 张）
if "%KEY%"=="show" echo       已拷同名标注 JSON %JCNT% 份（无 JSON 的图在列表页显示「未标」）
if "%KEY%"=="prelabel" echo       标注目录留空：每张图预标注都会全新产出
echo       data\records 留空
if "%CNT%"=="0" goto :no_img

echo [4/5] 处理权重...
if "%KEY%"=="prelabel" goto :weights_copy
if exist "%DST%\weights" rd /s /q "%DST%\weights"
echo       展示模式不拷权重（预标注页在此模式下不可用）
goto :launch

:weights_copy
rem 含 clip\ViT-B-32.pt：YOLO-World 设类别要用 CLIP 文本编码器，缺了会尝试联网下载
robocopy "%SRC%\weights" "%DST%\weights" /MIR /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :weights_fail
if not exist "%DST%\weights\yolo26n-seg.pt" goto :weights_fail
if not exist "%DST%\weights\yolov8s-worldv2.pt" goto :weights_fail
if not exist "%DST%\weights\clip\ViT-B-32.pt" goto :weights_fail
echo       已拷 weights\yolo26n-seg.pt、yolov8s-worldv2.pt、clip\ViT-B-32.pt

:launch
echo [5/5] 启动副本服务...
echo ============================================================
echo  浏览器打开：http://127.0.0.1:%PORT%
if "%KEY%"=="show" echo  展示模式：有 %CNT% 张图（%JCNT% 张带现成标注）可录仪表盘/列表/画布操作
if "%KEY%"=="prelabel" echo  预标注模式：%CNT% 张图、标注为空，可在「预标注」页设阈值跑批
if "%KEY%"=="prelabel" echo  每次跑前（换下一档阈值前）先另开窗口运行 5001隔离reset.bat 清空副本标注
if "%KEY%"=="prelabel" echo  阈值对比：powershell -ExecutionPolicy Bypass -File "%~dp0读取副本统计.ps1"
echo  在此窗口按 Ctrl+C 停止服务；5000 正式服务不受影响
echo  用完删除副本：rd /s /q "%DST%"
echo ============================================================
cd /d "%DST%"
"%PY%" -c "import app; app.app.run(port=%PORT%)"
echo 副本服务已停止。用完删除副本：rd /s /q "%DST%"
if not defined NO_PAUSE pause
exit /b 0

rem 每张图调用一次：取前 N 张；展示模式连带拷同名 JSON
:take
if %CNT% geq %N% exit /b 0
copy /y "%SRC%\data\curated\images\%~1" "%DST%\data\curated\images\" >nul
set /a CNT+=1
if not "%KEY%"=="show" exit /b 0
if not exist "%SRC%\data\annotations\%~n1.json" exit /b 0
copy /y "%SRC%\data\annotations\%~n1.json" "%DST%\data\annotations\" >nul
set /a JCNT+=1
exit /b 0

:bad_mode
echo [错误] 未知模式：%MODE%
echo        用法：5001隔离启动.bat demo-展示   或   5001隔离启动.bat demo-预标注
goto :fail

:no_src
echo [错误] 找不到项目根 app.py：%SRC%
goto :fail

:no_py
echo [错误] 找不到 imglabel 环境的 python：%PY%
goto :fail

:port_busy
echo [错误] 端口 %PORT% 已被占用（最后一列为 PID）：
netstat -ano | findstr /R /C:":%PORT% .*LISTENING"
echo        请先关闭上次的 5001 窗口或占用该端口的程序后重试。
echo        本脚本不会自动结束任何进程。
goto :fail

:copy_fail
echo [错误] robocopy 复制项目代码失败
goto :fail

:no_img
echo [错误] 没有拷到任何图片：%SRC%\data\curated\images
goto :fail

:weights_fail
echo [错误] 复制权重失败或副本缺少权重文件：%DST%\weights
goto :fail

:fail
if not defined NO_PAUSE pause
exit /b 1
