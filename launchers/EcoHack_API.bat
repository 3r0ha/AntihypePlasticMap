@echo off
title EcoHack API Server
cd /d "%~dp0.."
echo ========================================
echo   EcoHack API Server
echo   http://localhost:8000/docs
echo ========================================
echo.
start http://localhost:8000/docs
python apps\api.py
if errorlevel 1 (
    echo.
    echo Ошибка! pip install fastapi uvicorn
    pause
)
