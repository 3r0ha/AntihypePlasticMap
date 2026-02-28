#!/bin/bash
cd "$(dirname "$0")/.."
echo "========================================"
echo "  Установка зависимостей EcoHack"
echo "========================================"
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
echo ""
echo "========================================"
echo "  Установка завершена!"
echo "========================================"
