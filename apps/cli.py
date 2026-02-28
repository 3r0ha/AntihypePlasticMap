#!/usr/bin/env python3
"""antihype Plastic Map — Command Line Interface."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.processor import run_pipeline
from viz.maps import make_folium_map
from viz.plots import make_static_png
from config import DEFAULT_BUFFER_DEG, DEFAULT_DAYS_BACK, MAX_CLOUD_COVER, OUTPUT_DIR, PRESETS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="antihype: автоматическая карта пластика по спутниковым снимкам",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python apps/cli.py --lat 28.5 --lon -145.0
  python apps/cli.py --preset pacific --days 7
  python apps/cli.py --lat 27 --lon -65 --days 5 --cloud 90 --output ./results

Доступные пресеты:
  kochi        — Кочи, Индия (10°N, 76.3°E)
  mumbai       — Мумбаи, Индия (19°N, 72.9°E)
  singapore    — Сингапурский пролив (1.3°N, 103.8°E)
  durban       — Дурбан, ЮАР (29.9°S, 31.1°E)
  med          — Средиземное море (37°N, 13°E)
  chennai      — Ченнай, Индия (13.1°N, 80.3°E)
  jakarta      — Джакарта, Индонезия (6.1°S, 106.9°E)
  osaka        — Осакский залив, Япония
        """,
    )

    loc_group = parser.add_mutually_exclusive_group(required=True)
    loc_group.add_argument(
        "--preset", choices=list(PRESETS.keys()),
        help="Использовать предустановленный район"
    )
    loc_group.add_argument(
        "--lat", type=float,
        help="Широта центра (°N)"
    )

    parser.add_argument("--lon", type=float, help="Долгота центра (°E)")
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS_BACK,
        help=f"Период поиска (дней назад, по умолч. {DEFAULT_DAYS_BACK})"
    )
    parser.add_argument(
        "--buffer", type=float, default=DEFAULT_BUFFER_DEG,
        help=f"Размер области в градусах (по умолч. {DEFAULT_BUFFER_DEG})"
    )
    parser.add_argument(
        "--cloud", type=int, default=MAX_CLOUD_COVER,
        help=f"Макс. облачность снимка %% (по умолч. {MAX_CLOUD_COVER})"
    )
    parser.add_argument(
        "--output", type=str, default=OUTPUT_DIR,
        help=f"Папка для сохранения результатов (по умолч. {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--no-html", action="store_true",
        help="Не создавать HTML карту"
    )
    parser.add_argument(
        "--no-png", action="store_true",
        help="Не создавать PNG карту"
    )
    parser.add_argument(
        "--temporal", action="store_true", default=False,
        help="Включить темпоральную аномалию"
    )
    parser.add_argument(
        "--no-drift", action="store_true", default=False,
        help="Отключить коррекцию дрейфа"
    )
    parser.add_argument(
        "--route", action="store_true", default=False,
        help="Построить оптимальный маршрут к горячим точкам"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Подробный вывод"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Вывести результат в формате JSON и завершить"
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if getattr(args, 'json', False):
        logging.disable(logging.CRITICAL)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    quiet = getattr(args, 'json', False)

    if args.preset:
        lat, lon, name = PRESETS[args.preset]
        if not quiet:
            print(f"\n📍 Пресет: {name}")
            print(f"   Координаты: {lat}°N, {lon}°E")
    else:
        if args.lon is None:
            print("❌ Ошибка: необходимо указать --lon при использовании --lat")
            sys.exit(1)
        lat, lon = args.lat, args.lon
        if not quiet:
            print(f"\n📍 Координаты: {lat}°N, {lon}°E")

    if not quiet:
        print(f"📅 Период: последние {args.days} дней")
        print(f"🗺️  Область: ±{args.buffer}° (~{args.buffer * 111:.0f} км)")
        print(f"☁️  Макс. облачность: {args.cloud}%\n")

    def progress(msg: str, pct: int):
        if quiet:
            return
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[{bar}] {pct:3d}% {msg}", end="", flush=True)

    result = run_pipeline(
        lat=lat,
        lon=lon,
        days_back=args.days,
        buffer=args.buffer,
        max_cloud_cover=args.cloud,
        progress_cb=progress,
        enable_temporal=args.temporal,
        enable_drift=not args.no_drift,
    )
    print()

    if not result.success:
        if quiet:
            print(json.dumps({"success": False, "warnings": result.warnings}))
            sys.exit(1)
        print("\n⚠️  Снимки не найдены!")
        for w in result.warnings:
            print(f"   {w}")
        print("\nСовет: увеличьте --days или --cloud")
        sys.exit(1)

    stats = result.stats

    if quiet:
        output = {
            "success": True,
            "lat": lat, "lon": lon,
            "scenes_found": result.scenes_found,
            "scene_dates": result.scene_dates,
            "stats": stats,
            "hotspots": result.hotspots,
            "hotspots_drift_corrected": result.hotspots_drift_corrected,
            "warnings": result.warnings,
            "processing_time_sec": result.processing_time_sec,
        }
        print(json.dumps(output, default=str, ensure_ascii=False, indent=2))
        sys.exit(0)

    for w in result.warnings:
        print(f"⚠️  {w}")

    print(f"\n{'='*50}")
    print(f"✅ РЕЗУЛЬТАТЫ")
    print(f"{'='*50}")
    print(f"🛰️  Найдено снимков:     {result.scenes_found}")
    print(f"📅 Даты снимков:        {', '.join(result.scene_dates)}")
    print(f"🔴 Покрытие пластиком:  {stats.get('plastic_coverage_pct', 0):.3f}%")
    print(f"☁️  Облачность:          {stats.get('cloud_coverage_pct', '?')}%")
    fdi_max = stats.get("fdi_max")
    if fdi_max is not None:
        print(f"📈 FDI макс:            {fdi_max:.4f}")
    print(f"⏱️  Время обработки:     {result.processing_time_sec} с")
    print(f"📊 FDI порог:           {stats.get('fdi_threshold_used', '?')}")
    print(f"🎯 Уверенность:         {stats.get('confidence_mean', 0):.1%}")
    print(f"✨ Glint пикселей:      {stats.get('glint_pixels', 0)}")
    print(f"🔥 Горячих точек:       {len(result.hotspots)}")
    print(f"{'='*50}\n")

    hotspots = result.hotspots

    if hotspots and not args.no_drift:
        from core.drift import simulate_drift
        from core.currents import get_ocean_currents
        top_hs = hotspots[0]
        try:
            currents = get_ocean_currents(top_hs["lat"], top_hs["lon"], buffer=2.0)
            drift = simulate_drift(top_hs["lat"], top_hs["lon"], currents, hours=48)
            print(f"{'='*50}")
            print(f"🌊 ДРЕЙФ (горячая точка #1)")
            print(f"{'='*50}")
            print(f"   Начало:     {drift.origin_lat:.4f}°N, {drift.origin_lon:.4f}°E")
            if drift.positions_24h:
                print(f"   Через 24ч:  {drift.positions_24h[0]:.4f}°N, {drift.positions_24h[1]:.4f}°E  ({drift.distance_km_24h:.1f} км)")
            if drift.positions_48h:
                print(f"   Через 48ч:  {drift.positions_48h[0]:.4f}°N, {drift.positions_48h[1]:.4f}°E  ({drift.distance_km_48h:.1f} км)")
            print(f"   Скорость течения: {drift.current_speed_ms:.3f} м/с  |  Направление: {drift.current_direction_deg:.1f}°")
            print(f"   Источник данных:  {drift.source}")
            print(f"{'='*50}\n")
        except Exception as e:
            print(f"⚠️  Ошибка расчёта дрейфа: {e}")

    if hotspots and args.route:
        from core.route import plan_route
        try:
            route = plan_route(lat, lon, hotspots)
            print(f"{'='*50}")
            print(f"🧭 МАРШРУТ  ({route.n_waypoints if hasattr(route, 'n_waypoints') else len(route.waypoints)} точек, {route.total_distance_km:.1f} км, ~{route.total_eta_hours:.1f} ч)")
            print(f"{'='*50}")
            print(f"  {'#':>3}  {'Метка':<18}  {'Широта':>9}  {'Долгота':>10}  {'Курс':>6}  {'Км':>7}  {'ETA ч':>6}")
            print(f"  {'-'*3}  {'-'*18}  {'-'*9}  {'-'*10}  {'-'*6}  {'-'*7}  {'-'*6}")
            for i, wp in enumerate(route.waypoints, 1):
                bearing = f"{wp.bearing_from_prev_deg:.0f}°" if wp.bearing_from_prev_deg is not None else "  —"
                dist = f"{wp.distance_from_prev_km:.1f}" if wp.distance_from_prev_km is not None else "  —"
                eta = f"{wp.eta_hours:.1f}" if wp.eta_hours is not None else "  —"
                print(f"  {i:>3}  {wp.label:<18}  {wp.lat:>9.4f}  {wp.lon:>10.4f}  {bearing:>6}  {dist:>7}  {eta:>6}")
            print(f"{'='*50}\n")
        except Exception as e:
            print(f"⚠️  Ошибка планирования маршрута: {e}")

    os.makedirs(args.output, exist_ok=True)
    base_name = f"plastic_map_{lat:.2f}_{lon:.2f}_{args.days}d"

    if not args.no_html:
        html_path = os.path.join(args.output, f"{base_name}.html")
        make_folium_map(
            lat=lat, lon=lon,
            fdi=result.fdi,
            plastic_mask=result.plastic_mask,
            lons=result.lons,
            lats=result.lats,
            cloud_mask=result.cloud_mask,
            stats=stats,
            scene_dates=result.scene_dates,
            output_path=html_path,
            hotspots=result.hotspots,
        )
        print(f"🗺️  HTML карта: {html_path}")

    if not args.no_png:
        png_path = os.path.join(args.output, f"{base_name}.png")
        make_static_png(
            fdi=result.fdi,
            plastic_mask=result.plastic_mask,
            lons=result.lons,
            lats=result.lats,
            lat=lat, lon=lon,
            cloud_mask=result.cloud_mask,
            stats=stats,
            scene_dates=result.scene_dates,
            output_path=png_path,
        )
        print(f"🖼️  PNG карта:  {png_path}")

    print("\n✅ Готово!")


if __name__ == "__main__":
    main()
