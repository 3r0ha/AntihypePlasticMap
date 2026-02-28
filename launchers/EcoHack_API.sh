#!/bin/bash
cd "$(dirname "$0")/.."
echo "========================================"
echo "  EcoHack API Server"
echo "  http://localhost:8000/docs"
echo "========================================"
python3 apps/api.py || {
    echo "Ошибка! pip3 install fastapi uvicorn"
    read -p "Нажмите Enter..."
}
