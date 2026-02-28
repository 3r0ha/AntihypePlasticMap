@echo off
title EcoHack Lite
cd /d "%~dp0.."
echo ========================================
echo   EcoHack Lite - Карта пластика
echo   http://localhost:8090
echo ========================================
echo.
python apps\lite_gui.py
if errorlevel 1 (
    echo.
    echo Ошибка! Убедитесь что Python установлен и зависимости установлены:
    echo   pip install -r requirements.txt
    echo.
    pause
)
