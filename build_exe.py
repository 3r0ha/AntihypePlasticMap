#!/usr/bin/env python3
"""
EcoHack — Build .exe files using PyInstaller.

Usage:
    python build_exe.py          # Build both
    python build_exe.py --lite   # Build Lite only
    python build_exe.py --full   # Build Full only
"""
import argparse
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))


def build_lite():
    """Build EcoHack Lite (Bottle + browser GUI)."""
    print("=" * 60)
    print("  Building EcoHack Lite...")
    print("=" * 60)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "EcoHack_Lite",
        "--add-data", f"config.py{os.pathsep}.",
        "--add-data", f"core{os.pathsep}core",
        "--add-data", f"viz{os.pathsep}viz",
        "--hidden-import", "bottle",
        "--hidden-import", "numpy",
        "--hidden-import", "matplotlib",
        "--hidden-import", "PIL",
        "--hidden-import", "scipy",
        "--hidden-import", "xarray",
        "--hidden-import", "rasterio",
        "--hidden-import", "pyproj",
        "--hidden-import", "pystac_client",
        "--hidden-import", "planetary_computer",
        "--hidden-import", "stackstac",
        "--hidden-import", "dask",
        "--hidden-import", "pandas",
        "--clean",
        "--noconfirm",
        os.path.join("apps", "lite_gui.py"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    exe_path = os.path.join(ROOT, "dist", "EcoHack_Lite.exe" if sys.platform == "win32" else "EcoHack_Lite")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n  OK: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"\n  Built: dist/EcoHack_Lite")


def build_full():
    """Build EcoHack Full (Streamlit wrapper)."""
    print("=" * 60)
    print("  Building EcoHack Full (Streamlit)...")
    print("=" * 60)

    spec_path = os.path.join(ROOT, "ecohack_full.spec")
    if os.path.exists(spec_path):
        cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", spec_path]
    else:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--name", "EcoHack_Full",
            "--add-data", f"config.py{os.pathsep}.",
            "--add-data", f"core{os.pathsep}core",
            "--add-data", f"viz{os.pathsep}viz",
            "--add-data", f"apps{os.pathsep}apps",
            "--collect-all", "streamlit",
            "--collect-all", "altair",
            "--hidden-import", "streamlit",
            "--hidden-import", "folium",
            "--hidden-import", "branca",
            "--hidden-import", "numpy",
            "--hidden-import", "matplotlib",
            "--hidden-import", "PIL",
            "--hidden-import", "scipy",
            "--hidden-import", "xarray",
            "--hidden-import", "rasterio",
            "--hidden-import", "pyproj",
            "--hidden-import", "pystac_client",
            "--hidden-import", "planetary_computer",
            "--hidden-import", "stackstac",
            "--hidden-import", "dask",
            "--hidden-import", "pandas",
            "--hidden-import", "reportlab",
            "--clean",
            "--noconfirm",
            os.path.join("apps", "streamlit_runner.py"),
        ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    exe_path = os.path.join(ROOT, "dist", "EcoHack_Full.exe" if sys.platform == "win32" else "EcoHack_Full")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n  OK: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"\n  Built: dist/EcoHack_Full")


def main():
    parser = argparse.ArgumentParser(description="Build EcoHack .exe files")
    parser.add_argument("--lite", action="store_true", help="Build Lite only")
    parser.add_argument("--full", action="store_true", help="Build Full only")
    args = parser.parse_args()

    if not args.lite and not args.full:
        args.lite = args.full = True

    if args.lite:
        build_lite()
    if args.full:
        build_full()

    print("\n" + "=" * 60)
    print("  Build complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
