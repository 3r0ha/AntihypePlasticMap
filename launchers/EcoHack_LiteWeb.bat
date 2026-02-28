@echo off
title EcoHack Lite Web
cd /d "%~dp0.."
echo ========================================
echo   EcoHack Lite Web (спутниковый интернет)
echo   http://localhost:8088
echo ========================================
echo.
start http://localhost:8088
python apps\lite_web.py
if errorlevel 1 (
    echo Ошибка! pip install bottle
    pause
)
