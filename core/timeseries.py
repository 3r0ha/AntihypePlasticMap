"""Multi-temporal analysis: track plastic accumulation trends over multiple date windows."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesFrame:
    """Single time step in the time series."""
    date: str
    fdi: Optional[np.ndarray] = None
    plastic_mask: Optional[np.ndarray] = None
    plastic_coverage_pct: float = 0.0
    plastic_area_km2: float = 0.0
    fdi_mean: Optional[float] = None
    fdi_max: Optional[float] = None
    cloud_coverage_pct: float = 0.0
    scenes_found: int = 0
    valid: bool = False


@dataclass
class TimeSeriesResult:
    """Full time series analysis result."""
    lat: float
    lon: float
    frames: list[TimeSeriesFrame] = field(default_factory=list)
    lons: Optional[np.ndarray] = None
    lats_arr: Optional[np.ndarray] = None

    trend_direction: str = "unknown"
    trend_slope_pct_per_day: float = 0.0
    coverage_change_pct: float = 0.0

    @property
    def dates(self) -> list[str]:
        return [f.date for f in self.frames if f.valid]

    @property
    def coverage_series(self) -> list[float]:
        return [f.plastic_coverage_pct for f in self.frames if f.valid]

    @property
    def area_series(self) -> list[float]:
        return [f.plastic_area_km2 for f in self.frames if f.valid]

    @property
    def fdi_mean_series(self) -> list[float]:
        return [f.fdi_mean or 0.0 for f in self.frames if f.valid]


def run_timeseries(
    lat: float,
    lon: float,
    n_periods: int = 5,
    days_per_period: int = 3,
    buffer: float = 0.5,
    progress_cb: Optional[Callable[[str, int], None]] = None,
) -> TimeSeriesResult:
    """Run FDI analysis for multiple time windows and compute trend."""
    import pystac_client
    import planetary_computer

    from core.data_loader import (
        load_bands,
        make_bbox,
        get_scene_metadata,
        REQUIRED_BANDS,
    )
    from core.cloud_mask import apply_cloud_mask, make_composite
    from core.indices import compute_all_indices, compute_stats
    from core.processor import _auto_scale_composite
    from config import PC_STAC_URL, S2_COLLECTION, MAX_CLOUD_COVER, TARGET_RESOLUTION

    def progress(msg: str, pct: int):
        logger.info(f"[{pct}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    result = TimeSeriesResult(lat=lat, lon=lon)
    frames = []
    bbox = make_bbox(lat, lon, buffer)

    # Open STAC catalog once and reuse across all periods.
    catalog = pystac_client.Client.open(
        PC_STAC_URL,
        modifier=planetary_computer.sign_inplace,
    )

    for i in range(n_periods - 1, -1, -1):
        end_date = datetime.utcnow() - timedelta(days=i * days_per_period)
        start_date = end_date - timedelta(days=days_per_period)
        date_label = end_date.strftime("%Y-%m-%d")
        date_range = (
            f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
        )

        pct = int(10 + 80 * (n_periods - i) / n_periods)
        progress(f"Период {n_periods - i}/{n_periods}: {date_label}...", pct)

        frame = TimeSeriesFrame(date=date_label)

        try:
            search = catalog.search(
                collections=[S2_COLLECTION],
                bbox=bbox,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}},
                sortby=[{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            )
            items = list(search.items())
            frame.scenes_found = len(items)

            if items:
                stack = load_bands(items, lat, lon, buffer, TARGET_RESOLUTION)

                if stack is not None:
                    masked, cloud_mask_da = apply_cloud_mask(stack)
                    composite = make_composite(masked, cloud_mask_da)
                    cloud_composite = cloud_mask_da.mean(dim="time").compute()

                    composite, _ = _auto_scale_composite(composite)

                    indices = compute_all_indices(composite)
                    fdi_raw = indices["fdi"].compute()
                    plastic_raw = indices["plastic_mask"].compute()

                    stats = compute_stats(fdi_raw, plastic_raw, cloud_composite)

                    frame.fdi = fdi_raw.values
                    frame.plastic_mask = plastic_raw.values.astype(bool)
                    frame.plastic_coverage_pct = stats.get("plastic_coverage_pct", 0.0)
                    frame.plastic_area_km2 = stats.get("plastic_area_km2", 0.0)
                    frame.fdi_mean = stats.get("fdi_mean")
                    frame.fdi_max = stats.get("fdi_max")
                    frame.cloud_coverage_pct = stats.get("cloud_coverage_pct", 0.0)
                    frame.valid = True

                    if result.lons is None:
                        result.lons = fdi_raw.x.values
                        result.lats_arr = fdi_raw.y.values

        except Exception as e:
            logger.warning(f"Period {date_label} failed: {e}")
            frame.valid = False

        frames.append(frame)

    result.frames = frames

    valid_frames = [f for f in frames if f.valid]
    if len(valid_frames) >= 2:
        coverages = [f.plastic_coverage_pct for f in valid_frames]
        n = len(coverages)
        x = np.arange(n)
        if n > 1:
            slope = float(np.polyfit(x, coverages, 1)[0])
            result.trend_slope_pct_per_day = round(slope / days_per_period, 4)
            result.coverage_change_pct = round(coverages[-1] - coverages[0], 4)

            if abs(slope) < 0.001:
                result.trend_direction = "stable"
            elif slope > 0:
                result.trend_direction = "increasing"
            else:
                result.trend_direction = "decreasing"

    progress("Временной анализ завершён", 100)
    return result
