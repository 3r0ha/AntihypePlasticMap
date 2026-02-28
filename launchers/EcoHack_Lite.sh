#!/bin/bash
cd "$(dirname "$0")/.."
echo "========================================"
echo "  EcoHack Lite - Карта пластика"
echo "  http://localhost:8090"
echo "========================================"
python3 apps/lite_gui.py || {
    echo ""
    echo "Ошибка! Установите зависимости: pip3 install -r requirements.txt"
    read -p "Нажмите Enter..."
}
