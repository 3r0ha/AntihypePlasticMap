"""Main processing pipeline: coordinates to FDI map + confidence + drift-corrected hotspots."""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Callable, Optional

import numpy as np
import xarray as xr

from .cloud_mask import apply_cloud_mask, make_composite, select_least_cloudy
from .data_loader import get_scene_metadata, get_sentinel2_data
from .indices import (
    apply_morphological_filter,
    compute_all_indices,
    compute_confidence_map,
    compute_fdi,
    compute_stats,
    find_hotspots,
)
from config import (
    DEFAULT_BUFFER_DEG,
    DEFAULT_DAYS_BACK,
    FALLBACK_DAYS_BACK,
    MAX_CLOUD_COVER,
    MIN_CLUSTER_PIXELS,
)

logger = logging.getLogger(__name__)

_result_cache = {}
_CACHE_TTL = 3600
_CACHE_MAX_SIZE = 10


@dataclass
class PipelineResult:
    """Container for all pipeline outputs."""
    lat: float
    lon: float
    days_back: int

    fdi: Optional[np.ndarray] = None
    ndwi: Optional[np.ndarray] = None
    plastic_mask: Optional[np.ndarray] = None
    confidence_map: Optional[np.ndarray] = None
    cloud_mask: Optional[np.ndarray] = None
    glint_mask: Optional[np.ndarray] = None

    fdi_anomaly: Optional[np.ndarray] = None

    lons: Optional[np.ndarray] = None
    lats: Optional[np.ndarray] = None

    scenes_found: int = 0
    scenes_used: int = 0
    scene_dates: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    hotspots: list = field(default_factory=list)
    hotspots_drift_corrected: list = field(default_factory=list)
    fdi_threshold_used: float = 0.0
    processing_time_sec: float = 0.0
    warnings: list = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.fdi is not None and self.scenes_found > 0


def _auto_scale_composite(composite: xr.DataArray) -> tuple[xr.DataArray, bool]:
    """Scale raw DN values to reflectance (0-1) if median B08 > 100."""
    sample_b08 = composite.sel(band="B08").values
    valid_vals = sample_b08[~np.isnan(sample_b08)]

    if valid_vals.size > 0 and np.nanmedian(valid_vals) > 100:
        logger.info("Detected DN values (median B08=%.1f), scaling by /10000", np.nanmedian(valid_vals))
        spectral_bands = [b for b in composite.band.values if b != "SCL"]
        spectral = composite.sel(band=spectral_bands) / 10000.0
        scl = composite.sel(band=["SCL"]) if "SCL" in composite.band.values else None
        if scl is not None:
            composite = xr.concat([spectral, scl], dim="band")
        else:
            composite = spectral
        return composite, True

    return composite, False


def _compute_temporal_baseline(
    lat: float,
    lon: float,
    buffer: float,
    resolution: int,
    current_composite: xr.DataArray,
) -> Optional[xr.DataArray]:
    """
    Compute 90-day median FDI baseline.
    Subtracting from current FDI reveals only new/transient anomalies (debris).
    """
    try:
        stack_bg, items_bg = get_sentinel2_data(
            lat, lon,
            days_back=FALLBACK_DAYS_BACK,
            buffer=buffer,
            max_cloud_cover=MAX_CLOUD_COVER,
            resolution=resolution,
            max_items=5,
        )

        if stack_bg is None or len(items_bg) < 2:
            logger.info("Not enough historical scenes for temporal baseline")
            return None

        masked_bg, cloud_bg = apply_cloud_mask(stack_bg)
        composite_bg = make_composite(masked_bg, cloud_bg)

        composite_bg, _ = _auto_scale_composite(composite_bg)

        fdi_baseline = compute_fdi(composite_bg).compute()
        logger.info(
            "Temporal baseline computed from %d scenes (%.0f-day window)",
            len(items_bg), FALLBACK_DAYS_BACK,
        )
        return fdi_baseline

    except Exception as e:
        logger.warning("Temporal baseline failed: %s", e)
        return None


def _drift_correct_hotspots(
    hotspots: list[dict],
    scene_date_str: str,
    lat: float,
    lon: float,
) -> list[dict]:
    """Correct hotspot positions for ocean drift since image capture time."""
    if not hotspots:
        return []

    try:
        from .currents import get_ocean_currents
        from .drift import simulate_drift, haversine_km
    except ImportError:
        logger.warning("Drift modules unavailable, skipping correction")
        return hotspots

    try:
        scene_dt = datetime.strptime(scene_date_str, "%Y-%m-%d")
        hours_elapsed = (datetime.utcnow() - scene_dt).total_seconds() / 3600.0
        hours_elapsed = min(hours_elapsed, 72.0)
    except (ValueError, TypeError):
        logger.warning("Cannot parse scene date '%s', skipping drift", scene_date_str)
        return hotspots

    if hours_elapsed < 1.0:
        return hotspots

    try:
        currents = get_ocean_currents(lat, lon)
    except Exception as e:
        logger.warning("Cannot get currents for drift: %s", e)
        return hotspots

    corrected = []
    for hs in hotspots:
        try:
            drift_result = simulate_drift(
                hs["lat"], hs["lon"], currents,
                hours=round(hours_elapsed),
                dt_hours=0.5,
            )
            corrected_hs = dict(hs)
            corrected_hs["lat_original"] = hs["lat"]
            corrected_hs["lon_original"] = hs["lon"]
            corrected_hs["lat"] = round(drift_result.final_lat, 5)
            corrected_hs["lon"] = round(drift_result.final_lon, 5)
            corrected_hs["drift_hours"] = round(hours_elapsed, 1)
            corrected_hs["drift_km"] = round(
                haversine_km(hs["lat"], hs["lon"],
                             drift_result.final_lat, drift_result.final_lon),
                1,
            )
            corrected.append(corrected_hs)
        except Exception as e:
            logger.warning("Drift correction failed for hotspot %s: %s", hs, e)
            corrected.append(hs)

    return corrected


def run_pipeline(
    lat: float,
    lon: float,
    days_back: int = DEFAULT_DAYS_BACK,
    buffer: float = DEFAULT_BUFFER_DEG,
    max_cloud_cover: int = MAX_CLOUD_COVER,
    resolution: int = 60,
    max_scenes: int = 1,
    enable_temporal: bool = False,
    enable_drift: bool = True,
    progress_cb: Optional[Callable[[str, int], None]] = None,
) -> PipelineResult:
    """
    Full pipeline: search, load, mask, composite, indices, confidence,
    temporal anomaly, drift correction, stats.
    """
    t0 = time.time()

    cache_key = f"{round(lat,2)},{round(lon,2)},{days_back},{resolution},{enable_temporal},{enable_drift},{max_cloud_cover},{buffer}"
    if cache_key in _result_cache:
        cached_result, cached_ts = _result_cache[cache_key]
        if time.time() - cached_ts < _CACHE_TTL:
            logger.info("Returning cached pipeline result (key=%s)", cache_key)
            return cached_result
        else:
            del _result_cache[cache_key]

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        logger.warning(
            "Coordinates out of range (lat=%.4f, lon=%.4f), clamping to valid bounds",
            lat, lon,
        )
        lat = max(-90.0, min(90.0, lat))
        lon = max(-180.0, min(180.0, lon))

    def progress(msg: str, pct: int):
        logger.info(f"[{pct}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    result = PipelineResult(lat=lat, lon=lon, days_back=days_back)

    progress("Поиск спутниковых снимков...", 10)
    stack, items = get_sentinel2_data(
        lat, lon, days_back, buffer, max_cloud_cover,
        resolution=resolution, max_items=max_scenes,
    )

    if stack is None or len(items) == 0:
        result.warnings.append(
            f"Снимки не найдены за последние {days_back} дней. "
            "Попробуйте увеличить период или снизить требования к облачности."
        )
        result.processing_time_sec = time.time() - t0
        return result

    result.scenes_found = len(items)
    meta = get_scene_metadata(items)
    result.scene_dates = [m["date"] for m in meta]
    progress(f"Найдено снимков: {len(items)}", 20)

    progress("Маскировка облаков (SCL)...", 30)
    masked_stack, cloud_mask_da = apply_cloud_mask(stack)

    ny = stack.sizes.get("y", 0)
    nx = stack.sizes.get("x", 0)
    n_scenes = stack.sizes.get("time", 0)
    size_mpx = round(ny * nx / 1_000_000, 1)
    progress(
        f"Скачивание тайлов ({n_scenes} снимков, ~{size_mpx} Мпикс)… "
        "Это самый долгий шаг — обычно 1-3 мин",
        45,
    )
    composite = make_composite(masked_stack, cloud_mask_da)

    progress("Расчёт маски облачности...", 55)
    cloud_composite = cloud_mask_da.mean(dim="time").compute()
    result.scenes_used = len(stack.time)

    progress("Проверка масштаба данных...", 58)
    composite, was_scaled = _auto_scale_composite(composite)
    if was_scaled:
        result.warnings.append(
            "Данные масштабированы (DN → отражательная способность, /10000)"
        )

    progress("Расчёт спектральных индексов (FDI, NDWI, NDVI)...", 62)
    indices = compute_all_indices(composite)

    progress("Финальные вычисления → numpy...", 70)

    import dask
    import time as _time
    fdi_threshold = indices["fdi_threshold"]
    _MAX_RETRIES = 3
    _RETRY_DELAY_SEC = 5
    for _attempt in range(1, _MAX_RETRIES + 1):
        try:
            fdi_da, ndwi_da, plastic_da, glint_da = dask.compute(
                indices["fdi"], indices["ndwi"],
                indices["plastic_mask"], indices["glint_mask"],
            )
            break
        except Exception as _exc:
            if _attempt < _MAX_RETRIES:
                logger.warning(
                    "dask.compute() failed on attempt %d/%d: %s — retrying in %ds",
                    _attempt, _MAX_RETRIES, _exc, _RETRY_DELAY_SEC,
                )
                _time.sleep(_RETRY_DELAY_SEC)
            else:
                logger.error(
                    "dask.compute() failed after %d attempts: %s", _MAX_RETRIES, _exc
                )
                raise

    result.fdi = fdi_da.values
    result.ndwi = ndwi_da.values
    result.glint_mask = glint_da.values
    result.fdi_threshold_used = fdi_threshold

    progress("Фильтрация шума (морфологическая)...", 75)
    plastic_raw = plastic_da.values.astype(bool)
    result.plastic_mask = apply_morphological_filter(plastic_raw, MIN_CLUSTER_PIXELS)
    result.cloud_mask = cloud_composite.values

    progress("Расчёт карты уверенности...", 78)
    result.confidence_map = compute_confidence_map(fdi_da, result.plastic_mask, fdi_threshold)

    if enable_temporal:
        progress("Загрузка исторического фона (90 дней)...", 80)
        baseline_fdi = _compute_temporal_baseline(lat, lon, buffer, resolution, composite)
        if baseline_fdi is not None:
            try:
                result.fdi_anomaly = (fdi_da - baseline_fdi).values
                anomaly_positive = result.fdi_anomaly > 0
                n_new = int(anomaly_positive.sum())
                logger.info("Temporal anomaly: %d pixels above baseline", n_new)
            except Exception as e:
                logger.warning("Temporal anomaly computation failed: %s", e)

    progress("Преобразование координат...", 85)
    from pyproj import Transformer
    from core.data_loader import _utm_epsg
    epsg = _utm_epsg(lat, lon)
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)

    x_m = fdi_da.x.values
    y_m = fdi_da.y.values

    lons_1d, _ = transformer.transform(x_m, np.full_like(x_m, y_m[len(y_m)//2]))
    _, lats_1d = transformer.transform(np.full_like(y_m, x_m[len(x_m)//2]), y_m)

    result.lons = lons_1d
    result.lats = lats_1d

    progress("Вычисление статистики и поиск хотспотов...", 90)
    result.stats = compute_stats(
        fdi_da, result.plastic_mask, cloud_composite,
        pixel_size_m=resolution,
        confidence_map=result.confidence_map,
    )
    result.stats["fdi_threshold_used"] = round(fdi_threshold, 5)
    result.stats["glint_pixels"] = int(result.glint_mask.sum())

    result.hotspots = find_hotspots(
        result.fdi, result.plastic_mask, lats_1d, lons_1d,
        confidence_map=result.confidence_map,
    )

    if enable_drift and result.hotspots and result.scene_dates:
        progress("Коррекция хотспотов по течениям...", 95)
        result.hotspots_drift_corrected = _drift_correct_hotspots(
            result.hotspots,
            result.scene_dates[0],
            lat, lon,
        )
    else:
        result.hotspots_drift_corrected = result.hotspots

    result.processing_time_sec = round(time.time() - t0, 1)

    _result_cache[cache_key] = (result, time.time())
    if len(_result_cache) > _CACHE_MAX_SIZE:
        oldest = min(_result_cache, key=lambda k: _result_cache[k][1])
        del _result_cache[oldest]

    plastic_pct = result.stats.get("plastic_coverage_pct", 0)
    conf_mean = result.stats.get("confidence_mean", 0)
    n_hotspots = len(result.hotspots)
    progress(
        f"Готово! Пластик: {plastic_pct:.3f}%, "
        f"уверенность: {conf_mean:.1%}, хотспотов: {n_hotspots}",
        100,
    )
    return result
