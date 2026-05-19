@echo off
chcp 65001 >nul
echo === 番茄钟 Pomodoro Timer ===
echo.

set PYTHON="C:\Users\HLC\AppData\Local\Programs\Python\Python314\python.exe"

%PYTHON% "%~dp0pomodoro.py"
if %errorlevel% neq 0 (
    echo.
    echo 启动失败！请确认 Python 已安装: https://www.python.org/downloads/
    pause
)
