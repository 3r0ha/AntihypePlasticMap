@echo off
title EcoHack - Установка зависимостей
cd /d "%~dp0.."
echo ========================================
echo   Установка зависимостей EcoHack
echo ========================================
echo.
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo ========================================
echo   Установка завершена!
echo ========================================
pause
