@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem ============================================================
rem  5001 隔离沙箱 reset：只清空副本 %TEMP%\isolated_5001 的标注与修正记录
rem  prelabel 对已有 JSON 的图会跳过；清空后每次预标注都从零产出
rem  不碰真实项目；副本服务可保持运行，不必重启
rem  本文件为 GBK(936) 编码、不用 chcp 65001：cmd 按 UTF-8 读批处理时中文会错位成乱码命令，勿另存为 UTF-8
rem ============================================================
set "DST=%TEMP%\isolated_5001"
if not exist "%DST%\app.py" goto :no_dst
if not exist "%DST%\data\annotations" goto :no_ann

set /a A=0, R=0, LEFT=0
for %%F in ("%DST%\data\annotations\*.json") do set /a A+=1
for %%F in ("%DST%\data\records\*.json") do set /a R+=1
del /q "%DST%\data\annotations\*.json" 2>nul
if exist "%DST%\data\records" del /q "%DST%\data\records\*.json" 2>nul
for %%F in ("%DST%\data\annotations\*.json") do set /a LEFT+=1
if not "%LEFT%"=="0" goto :left

echo [完成] 已清空副本标注 %A% 个、修正记录 %R% 个
echo        副本：%DST%
echo        现在可在 http://127.0.0.1:5001 预标注页换下一档阈值重新跑批
echo        注意：预标注进行中请勿 reset，等进度条结束再清
if not defined NO_PAUSE pause
exit /b 0

:no_dst
echo [错误] 副本不存在：%DST%
echo        请先运行 5001隔离启动.bat demo-预标注
goto :fail

:no_ann
echo [错误] 副本缺少 data\annotations：%DST%
goto :fail

:left
echo [错误] 仍有 %LEFT% 个标注 JSON 未删除（可能被占用），请稍后重试
goto :fail

:fail
if not defined NO_PAUSE pause
exit /b 1
