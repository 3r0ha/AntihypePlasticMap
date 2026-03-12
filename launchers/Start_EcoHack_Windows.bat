@echo off
setlocal enabledelayedexpansion
title EcoHack Portable Launcher

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
    echo [OK] Портативный Python уже установлен.
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

echo [3/4] Настройка Pip...
:: В embed версии питона по умолчанию pip отключен. Надо раскомментировать import site
set "PTH_FILE=%PYTHON_DIR%\python310._pth"
powershell -Command "(Get-Content '%PTH_FILE%') -replace '#import site', 'import site' | Set-Content '%PTH_FILE%'"

powershell -Command "Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile 'get-pip.py'"
"%PYTHON_EXE%" get-pip.py
del "get-pip.py"

:check_reqs
echo [4/4] Проверка и установка зависимостей...
if not exist "%PYTHON_DIR%\.installed_reqs" (
    echo Устанавливаем библиотеки (это займет несколько минут)...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости.
        pause
        exit /b 1
    )
    echo done > "%PYTHON_DIR%\.installed_reqs"
) else (
    echo [OK] Зависимости уже установлены.
)

echo.
echo ====================================================
echo ВСЕ ГОТОВО! КАКОЕ ПРИЛОЖЕНИЕ ХОТИТЕ ЗАПУСТИТЬ?
echo ====================================================
echo 1 - EcoHack Full (Полноценный Streamlit интерфейс)
echo 2 - EcoHack Lite Web (Облегченная веб-версия)
echo 3 - EcoHack Lite GUI (Оконное приложение)
echo 4 - EcoHack API (Только сервер)
echo.

set /p choice="Введите номер (1-4) и нажмите Enter: "

if "%choice%"=="1" (
    echo Запуск Full (Streamlit)...
    "%PYTHON_EXE%" -m streamlit run apps\streamlit_app.py
) else if "%choice%"=="2" (
    echo Запуск Lite Web...
    "%PYTHON_EXE%" apps\lite_web.py
) else if "%choice%"=="3" (
    echo Запуск Lite GUI...
    "%PYTHON_EXE%" apps\lite_gui.py
) else if "%choice%"=="4" (
    echo Запуск API...
    "%PYTHON_EXE%" -m uvicorn apps.api:app --host 127.0.0.1 --port 8000
) else (
    echo Неверный выбор!
    pause
)

pause
