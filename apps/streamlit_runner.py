#!/usr/bin/env python3
"""antihype Full — Streamlit wrapper for PyInstaller .exe packaging."""
import os
import sys
import subprocess
import webbrowser
import threading
import time


def get_app_path():
    """Get path to streamlit_app.py, works in both dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "apps", "streamlit_app.py")


def open_browser():
    time.sleep(3)
    webbrowser.open("http://localhost:8501")


def main():
    app_path = get_app_path()
    print("=" * 50)
    print("  antihype Full (Streamlit)")
    print(f"  App: {app_path}")
    print("  http://localhost:8501")
    print("=" * 50)

    threading.Thread(target=open_browser, daemon=True).start()

    if getattr(sys, 'frozen', False):
        streamlit_bin = os.path.join(sys._MEIPASS, "streamlit")
    else:
        streamlit_bin = "streamlit"

    try:
        subprocess.run(
            [streamlit_bin, "run", app_path,
             "--server.port", "8501",
             "--server.headless", "true",
             "--browser.gatherUsageStats", "false"],
            check=True,
        )
    except KeyboardInterrupt:
        print("\nantihype Full остановлен.")
    except FileNotFoundError:
        print("Ошибка: streamlit не найден. Установите: pip install streamlit")
        sys.exit(1)


if __name__ == "__main__":
    main()
