#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "===================================================="
echo "       ECOHACK: АВТОМАТИЧЕСКИЙ ЗАПУСК"
echo "===================================================="
echo ""

# Используем Miniconda для изоляции
CONDA_DIR="$(pwd)/launchers/miniconda"
CONDA_EXE="$CONDA_DIR/bin/conda"
PYTHON_EXE="$CONDA_DIR/bin/python"

if [ ! -f "$PYTHON_EXE" ]; then
    echo "[1/4] Загрузка и установка переносного Python (Miniconda)..."
    
    if [ "$(uname)" == "Darwin" ]; then
        # macOS
        if [ "$(uname -m)" == "arm64" ]; then
            INSTALLER="Miniconda3-latest-MacOSX-arm64.sh"
        else
            INSTALLER="Miniconda3-latest-MacOSX-x86_64.sh"
        fi
    else
        # Linux
        if [ "$(uname -m)" == "aarch64" ]; then
            INSTALLER="Miniconda3-latest-Linux-aarch64.sh"
        else
            INSTALLER="Miniconda3-latest-Linux-x86_64.sh"
        fi
    fi

    curl -L -o miniconda.sh "https://repo.anaconda.com/miniconda/$INSTALLER"
    bash miniconda.sh -b -u -p "$CONDA_DIR"
    rm miniconda.sh
else
    echo "[OK] Переносной Python уже установлен."
fi

echo "[2/4] Проверка зависимостей..."
if [ ! -f "$CONDA_DIR/.installed_reqs" ]; then
    echo "Устанавливаем библиотеки (это займет несколько минут, не закрывайте окно!)..."
    "$PYTHON_EXE" -m pip install -r requirements.txt
    
    if [ $? -eq 0 ]; then
        touch "$CONDA_DIR/.installed_reqs"
        echo "[OK] Зависимости успешно установлены."
    else
        echo "[ОШИБКА] Не удалось установить зависимости. Попробуйте еще раз."
        exit 1
    fi
else
    echo "[OK] Зависимости уже установлены."
fi

echo ""
echo "===================================================="
echo "ВСЕ ГОТОВО! КАКОЕ ПРИЛОЖЕНИЕ ХОТИТЕ ЗАПУСТИТЬ?"
echo "===================================================="
echo "1 - EcoHack Full (Полноценный Streamlit интерфейс)"
echo "2 - EcoHack Lite Web (Облегченная веб-версия)"
echo "3 - EcoHack Lite GUI (Оконное приложение)"
echo "4 - EcoHack API (Только сервер)"
echo ""

read -p "Введите номер (1-4) и нажмите Enter: " choice

case $choice in
    1)
        echo "Запуск Full (Streamlit)..."
        "$PYTHON_EXE" -m streamlit run apps/streamlit_app.py
        ;;
    2)
        echo "Запуск Lite Web..."
        "$PYTHON_EXE" apps/lite_web.py
        ;;
    3)
        echo "Запуск Lite GUI..."
        "$PYTHON_EXE" apps/lite_gui.py
        ;;
    4)
        echo "Запуск API..."
        "$PYTHON_EXE" -m uvicorn apps.api:app --host 127.0.0.1 --port 8000
        ;;
    *)
        echo "Неверный выбор!"
        ;;
esac
