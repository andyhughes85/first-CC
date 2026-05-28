@echo off
chcp 65001 >nul
title 中线策略监控面板

cd /d "%~dp0"

echo ==========================================
echo  启动中线策略监控面板
echo ==========================================
echo 工作目录: %CD%
echo.

:: 检查 Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ 未找到 python，请确认已安装
    pause
    exit /b 1
)

:: 检查 streamlit
python -m streamlit --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Streamlit 未安装，运行: pip install streamlit
    pause
    exit /b 1
)

:: 检查端口是否已被占用
netstat -ano | findstr ":8520 " | findstr LISTEN >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [面板已在运行] 直接打开浏览器...
    start http://localhost:8520
    exit /b 0
)

echo [1/1] 启动 Streamlit (http://localhost:8520)...
start http://localhost:8520
python -m streamlit run app.py --server.port 8520

echo.
echo ❌ 面板已关闭
pause
