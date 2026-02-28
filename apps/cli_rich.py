#!/usr/bin/env python3
"""antihype Plastic Map — Rich CLI with beautiful terminal output."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.text import Text
from rich import box

from core.processor import run_pipeline
from viz.maps import make_folium_map
from viz.plots import make_static_png
from config import DEFAULT_BUFFER_DEG, DEFAULT_DAYS_BACK, MAX_CLOUD_COVER, OUTPUT_DIR, PRESETS

console = Console()

BANNER = """
[bold cyan]
 ███████╗ ██████╗ ██████╗ ██╗  ██╗ █████╗  ██████╗██╗  ██╗
 ██╔════╝██╔════╝██╔═══██╗██║  ██║██╔══██╗██╔════╝██║ ██╔╝
 █████╗  ██║     ██║   ██║███████║███████║██║     █████╔╝
 ██╔══╝  ██║     ██║   ██║██╔══██║██╔══██║██║     ██╔═██╗
 ███████╗╚██████╗╚██████╔╝██║  ██║██║  ██║╚██████╗██║  ██╗
 ╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝
[/bold cyan]
[dim]Детекция морского пластика по спутниковым снимкам Sentinel-2[/dim]
"""


def parse_args():
    parser = argparse.ArgumentParser(description="antihype Rich CLI")
    loc = parser.add_mutually_exclusive_group(required=True)
    loc.add_argument("--preset", choices=list(PRESETS.keys()))
    loc.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK)
    parser.add_argument("--buffer", type=float, default=DEFAULT_BUFFER_DEG)
    parser.add_argument("--cloud", type=int, default=MAX_CLOUD_COVER)
    parser.add_argument("--output", type=str, default=OUTPUT_DIR)
    parser.add_argument("--no-html", action="store_true")
    parser.add_argument("--no-png", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--temporal", action="store_true", help="Темпоральная аномалия")
    parser.add_argument("--no-drift", action="store_true", help="Отключить коррекцию дрейфа")
    parser.add_argument("--json", action="store_true", help="Вывести результат в формате JSON и завершить")
    return parser.parse_args()


def main():
    args = parse_args()

    quiet = getattr(args, 'json', False)

    if quiet:
        logging.disable(logging.CRITICAL)
    elif args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not quiet:
        console.print(Panel(BANNER, border_style="cyan", expand=False))

    if args.preset:
        lat, lon, name = PRESETS[args.preset]
        if not quiet:
            console.print(f"[bold]Пресет:[/bold] {name}")
    else:
        if args.lon is None:
            console.print("[red]Ошибка: укажите --lon[/red]")
            sys.exit(1)
        lat, lon = args.lat, args.lon

    if quiet:
        result = run_pipeline(
            lat=lat, lon=lon, days_back=args.days, buffer=args.buffer,
            max_cloud_cover=args.cloud, enable_temporal=args.temporal,
            enable_drift=not args.no_drift,
        )
        output = {
            "success": result.success,
            "lat": lat, "lon": lon,
            "scenes_found": result.scenes_found,
            "scene_dates": result.scene_dates,
            "stats": result.stats,
            "hotspots": result.hotspots,
            "hotspots_drift_corrected": result.hotspots_drift_corrected,
            "warnings": result.warnings,
            "processing_time_sec": result.processing_time_sec,
        }
        print(json.dumps(output, default=str, ensure_ascii=False, indent=2))
        sys.exit(0 if result.success else 1)

    params = Table(title="Параметры анализа", box=box.ROUNDED, border_style="blue")
    params.add_column("Параметр", style="cyan")
    params.add_column("Значение", style="white")
    params.add_row("Координаты", f"{lat:.4f}°N, {lon:.4f}°E")
    params.add_row("Период", f"{args.days} дней")
    params.add_row("Область", f"±{args.buffer}° (~{args.buffer * 111:.0f} км)")
    params.add_row("Макс. облачность", f"{args.cloud}%")
    params.add_row("Темпоральная", "Да" if args.temporal else "Нет")
    params.add_row("Коррекция дрейфа", "Нет" if args.no_drift else "Да")
    console.print(params)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Анализ...", total=100)

        def progress_cb(msg: str, pct: int):
            progress.update(task, completed=pct, description=msg)

        result = run_pipeline(
            lat=lat, lon=lon,
            days_back=args.days,
            buffer=args.buffer,
            max_cloud_cover=args.cloud,
            enable_temporal=args.temporal,
            enable_drift=not args.no_drift,
            progress_cb=progress_cb,
        )

    if not result.success:
        console.print(Panel("[red bold]Снимки не найдены![/red bold]\n" +
                           "\n".join(result.warnings),
                           title="Ошибка", border_style="red"))
        sys.exit(1)

    for w in result.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    stats = result.stats
    results = Table(title="Результаты анализа", box=box.DOUBLE_EDGE, border_style="green")
    results.add_column("Метрика", style="cyan", width=25)
    results.add_column("Значение", style="white bold")
    results.add_row("Снимков найдено", str(result.scenes_found))
    results.add_row("Даты снимков", ", ".join(result.scene_dates))
    results.add_row("Покрытие пластиком", f"{stats.get('plastic_coverage_pct', 0):.3f}%")
    results.add_row("Площадь пластика", f"{stats.get('plastic_area_km2', 0):.2f} км²")
    results.add_row("Облачность", f"{stats.get('cloud_coverage_pct', '?')}%")
    fdi_max = stats.get("fdi_max")
    if fdi_max is not None:
        results.add_row("FDI макс", f"{fdi_max:.5f}")
    results.add_row("FDI порог", f"{stats.get('fdi_threshold_used', '?')}")
    results.add_row("Уверенность (средн.)", f"{stats.get('confidence_mean', 0):.1%}")
    results.add_row("Glint пикселей", str(stats.get("glint_pixels", 0)))
    results.add_row("Горячих точек", str(len(result.hotspots)))
    results.add_row("Время обработки", f"{result.processing_time_sec} с")
    console.print(results)

    if result.hotspots:
        hs_table = Table(title="Горячие точки", box=box.SIMPLE, border_style="red")
        hs_table.add_column("#", style="dim")
        hs_table.add_column("Широта", style="cyan")
        hs_table.add_column("Долгота", style="cyan")
        hs_table.add_column("FDI макс", style="red")
        hs_table.add_column("Площадь км²", style="yellow")
        for i, hs in enumerate(result.hotspots[:10], 1):
            hs_table.add_row(
                str(i),
                f"{hs['lat']:.4f}°",
                f"{hs['lon']:.4f}°",
                f"{hs['fdi_max']:.5f}",
                f"{hs['area_km2']:.3f}",
            )
        console.print(hs_table)

    os.makedirs(args.output, exist_ok=True)
    base_name = f"plastic_map_{lat:.2f}_{lon:.2f}_{args.days}d"

    if not args.no_html:
        html_path = os.path.join(args.output, f"{base_name}.html")
        make_folium_map(
            lat=lat, lon=lon,
            fdi=result.fdi, plastic_mask=result.plastic_mask,
            lons=result.lons, lats=result.lats,
            cloud_mask=result.cloud_mask, stats=stats,
            scene_dates=result.scene_dates,
            hotspots=result.hotspots,
            output_path=html_path,
        )
        console.print(f"[green]HTML карта:[/green] {html_path}")

    if not args.no_png:
        png_path = os.path.join(args.output, f"{base_name}.png")
        make_static_png(
            fdi=result.fdi, plastic_mask=result.plastic_mask,
            lons=result.lons, lats=result.lats,
            lat=lat, lon=lon, cloud_mask=result.cloud_mask,
            stats=stats, scene_dates=result.scene_dates,
            output_path=png_path,
        )
        console.print(f"[green]PNG карта:[/green] {png_path}")

    console.print(Panel("[bold green]Готово![/bold green]", border_style="green"))


if __name__ == "__main__":
    main()
