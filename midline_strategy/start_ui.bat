@echo off
title Quant Dashboard
cd /d "%~dp0"

set PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PYTHON_CMD%" set PYTHON_CMD=python

netstat -ano | findstr ":8520 " | findstr LISTEN >nul
if errorlevel 1 goto start
echo Already running at http://localhost:8520
start http://localhost:8520
exit /b 0

:start
echo Starting dashboard...
start http://localhost:8520
%PYTHON_CMD% -m streamlit run app.py --server.port 8520
pause
