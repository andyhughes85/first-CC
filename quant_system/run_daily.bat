@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === A股中线波段买入信号 ===
echo %date% %time%
echo.

py main.py --today --push

echo.
echo 执行完毕
pause