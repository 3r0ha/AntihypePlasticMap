"""
Ocean surface current + wind data for drift simulation.
Sources: Open-Meteo (primary), HYCOM via ERDDAP (fallback), synthetic gyre (last resort).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# 2.5% of 10m wind speed -> plastic leeway (Isobe 2014)
# Biofouled plastic ~1-2%, clean light plastic ~3-4%
PLASTIC_WIND_LEEWAY = 0.025


def _dir_to_uv(speed: float, direction_deg: float) -> tuple[float, float]:
    """Convert speed + direction (oceanographic, going-TO) to u, v in m/s."""
    rad = math.radians(direction_deg)
    return speed * math.sin(rad), speed * math.cos(rad)


def _circular_mean_deg(directions: list[float]) -> float:
    """Mean of circular quantities (angles)."""
    sin_m = np.mean([math.sin(math.radians(d)) for d in directions])
    cos_m = np.mean([math.cos(math.radians(d)) for d in directions])
    return math.degrees(math.atan2(sin_m, cos_m)) % 360


def _fetch_open_meteo(
    lat: float,
    lon: float,
    buffer: float = 2.0,
    resolution: float = 0.5,
) -> Optional[dict]:
    """Fetch ocean currents and 10m wind from Open-Meteo on a grid."""
    try:
        import requests

        lats = np.arange(lat - buffer, lat + buffer + resolution, resolution)
        lons = np.arange(lon - buffer, lon + buffer + resolution, resolution)
        n = len(lats) * len(lons)

        flat_lats = [f"{lats[i]:.2f}" for i in range(len(lats)) for _ in range(len(lons))]
        flat_lons = [f"{lons[j]:.2f}" for _ in range(len(lats)) for j in range(len(lons))]
        lat_str = ",".join(flat_lats)
        lon_str = ",".join(flat_lons)

        marine_url = (
            "https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={lat_str}&longitude={lon_str}"
            "&hourly=ocean_current_velocity,ocean_current_direction"
            "&forecast_days=2&timeformat=iso8601"
        )
        r_marine = requests.get(marine_url, timeout=20)
        if r_marine.status_code != 200:
            logger.debug(f"Open-Meteo Marine: {r_marine.status_code}")
            return None

        marine_data = r_marine.json()
        if isinstance(marine_data, dict):
            marine_data = [marine_data]
        if len(marine_data) != n:
            logger.debug(f"Open-Meteo Marine: expected {n} points, got {len(marine_data)}")
            return None

        wind_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat_str}&longitude={lon_str}"
            "&hourly=wind_speed_10m,wind_direction_10m"
            "&wind_speed_unit=ms"
            "&forecast_days=2&timeformat=iso8601"
        )
        r_wind = requests.get(wind_url, timeout=20)
        wind_data = []
        if r_wind.status_code == 200:
            wd = r_wind.json()
            wind_data = wd if isinstance(wd, list) else [wd]

        u_grid = np.full((len(lats), len(lons)), np.nan)
        v_grid = np.full((len(lats), len(lons)), np.nan)
        wu_grid = np.zeros((len(lats), len(lons)))
        wv_grid = np.zeros((len(lats), len(lons)))

        for idx, pt in enumerate(marine_data):
            i = idx // len(lons)
            j = idx % len(lons)
            h = pt.get("hourly", {})
            speeds = [s for s in h.get("ocean_current_velocity", [])[:24] if s is not None]
            dirs = [d for d in h.get("ocean_current_direction", [])[:24] if d is not None]
            if not speeds:
                continue
            spd_ms = float(np.mean(speeds)) / 3.6  # Open-Meteo marine returns km/h
            direction = _circular_mean_deg(dirs)
            u_grid[i, j], v_grid[i, j] = _dir_to_uv(spd_ms, direction)

        if len(wind_data) == n:
            for idx, pt in enumerate(wind_data):
                i = idx // len(lons)
                j = idx % len(lons)
                h = pt.get("hourly", {})
                wspeeds = [s for s in h.get("wind_speed_10m", [])[:24] if s is not None]
                wdirs = [d for d in h.get("wind_direction_10m", [])[:24] if d is not None]
                if not wspeeds:
                    continue
                wspd = float(np.mean(wspeeds))
                wdir = _circular_mean_deg(wdirs)
                # Wind direction is meteorological (FROM), add 180 to convert to going-TO
                wu_grid[i, j], wv_grid[i, j] = _dir_to_uv(wspd, (wdir + 180) % 360)

        if np.all(np.isnan(u_grid)):
            return None

        u_fill = float(np.nanmean(u_grid)) if not np.all(np.isnan(u_grid)) else 0.0
        v_fill = float(np.nanmean(v_grid)) if not np.all(np.isnan(v_grid)) else 0.0
        u_grid = np.where(np.isnan(u_grid), u_fill, u_grid).astype("float32")
        v_grid = np.where(np.isnan(v_grid), v_fill, v_grid).astype("float32")

        return {
            "lats": lats,
            "lons": lons,
            "u": u_grid,
            "v": v_grid,
            "wind_u": wu_grid.astype("float32"),
            "wind_v": wv_grid.astype("float32"),
            "source": "Open-Meteo (CMEMS currents + GFS wind)",
            "is_synthetic": False,
        }

    except Exception as e:
        logger.debug(f"Open-Meteo fetch failed: {e}")
        return None


def _fetch_hycom_erddap(
    lat: float,
    lon: float,
    buffer: float = 2.0,
) -> Optional[dict]:
    """HYCOM via ERDDAP — currents only, no wind."""
    try:
        import requests
        from datetime import datetime, timedelta

        server = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=2)
        lat_min, lat_max = lat - buffer, lat + buffer
        lon_min, lon_max = lon - buffer, lon + buffer

        def url(ds, var):
            return (
                f"{server}/{ds}.json?{var}"
                f"[({start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}):1:({end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')})]"
                f"[({lat_min}):1:({lat_max})][({lon_min}):1:({lon_max})]"
            )

        ru = requests.get(url("HYCOM_sfc_u", "u"), timeout=20)
        rv = requests.get(url("HYCOM_sfc_v", "v"), timeout=20)
        if ru.status_code != 200 or rv.status_code != 200:
            return None

        rows_u = ru.json()["table"]["rows"]
        rows_v = rv.json()["table"]["rows"]
        if not rows_u:
            return None

        lats_set = sorted(set(r[1] for r in rows_u))
        lons_set = sorted(set(r[2] for r in rows_u))
        lats_arr, lons_arr = np.array(lats_set), np.array(lons_set)

        u_acc = np.zeros((len(lats_arr), len(lons_arr)))
        u_cnt = np.zeros_like(u_acc)
        v_sum = np.zeros_like(u_acc)
        v_cnt = np.zeros_like(u_acc)
        li = {v: i for i, v in enumerate(lats_set)}
        lj = {v: i for i, v in enumerate(lons_set)}

        for row in rows_u:
            i, j = li.get(row[1]), lj.get(row[2])
            if i is not None and j is not None and row[3] is not None:
                u_acc[i, j] += row[3]; u_cnt[i, j] += 1
        for row in rows_v:
            i, j = li.get(row[1]), lj.get(row[2])
            if i is not None and j is not None and row[3] is not None:
                v_sum[i, j] += row[3]; v_cnt[i, j] += 1

        u_grid = np.where(u_cnt > 0, u_acc / np.maximum(u_cnt, 1), np.nan)
        v_grid = np.where(v_cnt > 0, v_sum / np.maximum(v_cnt, 1), np.nan)
        wind_zero = np.zeros_like(u_grid, dtype="float32")

        return {
            "lats": lats_arr, "lons": lons_arr,
            "u": u_grid.astype("float32"), "v": v_grid.astype("float32"),
            "wind_u": wind_zero, "wind_v": wind_zero,
            "source": "HYCOM via ERDDAP (no wind)",
            "is_synthetic": False,
        }
    except Exception as e:
        logger.debug(f"HYCOM ERDDAP failed: {e}")
        return None


def _synthetic_currents(lat: float, lon: float, buffer: float = 2.0) -> dict:
    """Synthetic gyre + wind approximation for offline fallback."""
    resolution = 0.25
    lats = np.arange(lat - buffer, lat + buffer + resolution, resolution)
    lons = np.arange(lon - buffer, lon + buffer + resolution, resolution)
    lg, la = np.meshgrid(lons, lats)

    # Clockwise gyre (N hemisphere), counterclockwise in S
    u = 0.12 * np.cos(np.radians((la - lat) * 15)) * (-1)
    v = 0.07 * np.sin(np.radians((lg - lon) * 10))
    if lat < 0:
        u = -u
        v = -v

    rng = np.random.default_rng(42)
    u += rng.normal(0, 0.015, u.shape)
    v += rng.normal(0, 0.015, v.shape)

    wind_u = np.full_like(u, -3.5)  # synthetic NW wind ~5 m/s (typical trade winds)
    wind_v = np.full_like(v, -3.5)

    return {
        "lats": lats, "lons": lons,
        "u": u.astype("float32"), "v": v.astype("float32"),
        "wind_u": wind_u.astype("float32"), "wind_v": wind_v.astype("float32"),
        "source": "Synthetic (gyre model)",
        "is_synthetic": True,
    }


def get_ocean_currents(
    lat: float,
    lon: float,
    buffer: float = 2.0,
    prefer_synthetic: bool = False,
) -> dict:
    """Get ocean currents + wind. Priority: Open-Meteo, HYCOM, Synthetic."""
    if prefer_synthetic:
        return _synthetic_currents(lat, lon, buffer)

    result = _fetch_open_meteo(lat, lon, buffer)
    if result:
        logger.info(f"Currents+wind from Open-Meteo")
        return result

    result = _fetch_hycom_erddap(lat, lon, buffer)
    if result:
        logger.info("Currents from HYCOM (no wind)")
        return result

    logger.info("Using synthetic currents")
    return _synthetic_currents(lat, lon, buffer)
