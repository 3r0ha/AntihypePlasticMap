#!/bin/bash
cd "$(dirname "$0")/.."
echo "========================================"
echo "  EcoHack Full - Streamlit UI"
echo "  http://localhost:8501"
echo "========================================"
xdg-open http://localhost:8501 2>/dev/null &
streamlit run apps/streamlit_app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false || {
    echo ""
    echo "Ошибка! Установите: pip3 install streamlit"
    read -p "Нажмите Enter..."
}
