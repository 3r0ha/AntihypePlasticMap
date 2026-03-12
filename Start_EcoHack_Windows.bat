@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title EcoHack Portable Launcher

:: Переходим в папку проекта
cd /d "%~dp0"

:: Папка для портативного питона
set "PYTHON_DIR=%cd%\python_portable"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "PIP_EXE=%PYTHON_DIR%\Scripts\pip.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"
set "GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py"

echo ====================================================
echo        ECOHACK: АВТОМАТИЧЕСКИЙ ЗАПУСК
echo ====================================================
echo.

if exist "%PYTHON_EXE%" (
    echo [OK] Портативный Python найден.
    
    REM Проверка, успел ли установиться pip
    if not exist "%PYTHON_DIR%\Scripts\pip.exe" (
        echo [!] Замечена незавершенная установка Python. Восстановление...
        goto setup_pip
    )
    goto check_reqs
)

echo [1/4] Загрузка переносного Python...
mkdir "%PYTHON_DIR%" 2>nul
powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile 'python.zip'"
if not exist "python.zip" (
    echo [ОШИБКА] Не удалось скачать Python. Проверьте интернет.
    pause
    exit /b 1
)

echo [2/4] Распаковка Python...
powershell -Command "Expand-Archive -Path 'python.zip' -DestinationPath '%PYTHON_DIR%' -Force"
del "python.zip"

:setup_pip
echo [3/4] Настройка среды и PIP...
set "PTH_FILE=%PYTHON_DIR%\python310._pth"
powershell -Command "(Get-Content '%PTH_FILE%') -replace '#import site', 'import site' | Set-Content '%PTH_FILE%'"

powershell -Command "Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile 'get-pip.py'"
"%PYTHON_EXE%" get-pip.py
del "get-pip.py"

:check_reqs
echo [4/4] Проверка и установка зависимостей...
if not exist "%PYTHON_DIR%\.installed_reqs" (
    echo Устанавливаем библиотеки ^(это займет несколько минут, не закрывайте окно!^)...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости. Попробуйте еще раз.
        pause
        exit /b 1
    )
    echo done > "%PYTHON_DIR%\.installed_reqs"
    echo [OK] Зависимости успешно установлены.
) else (
    echo [OK] Зависимости уже установлены.
)

:menu
echo.
echo ====================================================
echo ВСЕ ГОТОВО! КАКОЕ ПРИЛОЖЕНИЕ ХОТИТЕ ЗАПУСТИТЬ?
echo ====================================================
echo 1 - EcoHack Full (Полноценный Streamlit интерфейс)
echo 2 - EcoHack Lite Web (Облегченная веб-версия)
echo 3 - EcoHack Lite GUI (Оконное приложение)
echo 4 - EcoHack API (Только сервер)
echo 5 - Выход
echo.

set /p choice="Введите номер (1-5) и нажмите Enter: "

if "%choice%"=="1" goto run_full
if "%choice%"=="2" goto run_lite_web
if "%choice%"=="3" goto run_lite_gui
if "%choice%"=="4" goto run_api
if "%choice%"=="5" exit /b 0

echo Неверный выбор!
goto menu

:run_full
echo Запуск Full (Streamlit)...
"%PYTHON_EXE%" apps\streamlit_runner.py
echo [Программа завершила работу]
pause
goto menu

:run_lite_web
echo Запуск Lite Web...
"%PYTHON_EXE%" apps\lite_web.py
echo [Программа завершила работу]
pause
goto menu

:run_lite_gui
echo Запуск Lite GUI...
"%PYTHON_EXE%" apps\lite_gui.py
echo [Программа завершила работу]
pause
goto menu

:run_api
echo Запуск API...
"%PYTHON_EXE%" -m uvicorn apps.api:app --host 127.0.0.1 --port 8000
echo [Программа завершила работу]
pause
goto menu
