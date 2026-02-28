@echo off
title EcoHack Full (Streamlit)
cd /d "%~dp0.."
echo ========================================
echo   EcoHack Full - Streamlit UI
echo   http://localhost:8501
echo ========================================
echo.
echo Запуск Streamlit...
start http://localhost:8501
streamlit run apps\streamlit_app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
if errorlevel 1 (
    echo.
    echo Ошибка! Убедитесь что Streamlit установлен:
    echo   pip install streamlit
    echo.
    pause
)
