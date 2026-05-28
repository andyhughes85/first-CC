@echo off
title Quant Dashboard
cd /d "%~dp0"

set PYTHON_CMD=
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do if exist %%p set PYTHON_CMD=%%p

if not defined PYTHON_CMD (
    where python >nul 2>&1 && set PYTHON_CMD=python
)

if not defined PYTHON_CMD (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

%PYTHON_CMD% -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Streamlit not installed
    pause
    exit /b 1
)

netstat -ano | findstr ":8520 " | findstr LISTEN >nul 2>&1
if not errorlevel 1 (
    start http://localhost:8520
    exit /b 0
)

start http://localhost:8520
%PYTHON_CMD% -m streamlit run app.py --server.port 8520

pause
\r