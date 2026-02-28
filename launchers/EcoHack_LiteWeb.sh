#!/bin/bash
cd "$(dirname "$0")/.."
echo "========================================"
echo "  EcoHack Lite Web (спутниковый интернет)"
echo "  http://localhost:8088"
echo "========================================"
python3 apps/lite_web.py || {
    echo "Ошибка! pip3 install bottle"
    read -p "Нажмите Enter..."
}
