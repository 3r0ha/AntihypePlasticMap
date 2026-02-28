"""Load Sentinel-2 L2A data from Microsoft Planetary Computer via STAC API."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
import stackstac
import xarray as xr

try:
    import planetary_computer
    import pystac_client
    HAS_PC = True
except ImportError:
    HAS_PC = False

from config import (
    DEFAULT_BUFFER_DEG,
    DEFAULT_DAYS_BACK,
    FALLBACK_DAYS_BACK,
    MAX_CLOUD_COVER,
    PC_STAC_URL,
    S2_COLLECTION,
    TARGET_RESOLUTION,
)

logger = logging.getLogger(__name__)

REQUIRED_BANDS = ["B03", "B04", "B06", "B08", "B8A", "B11", "B12", "SCL"]


def make_bbox(lat: float, lon: float, buffer: float = DEFAULT_BUFFER_DEG) -> List[float]:
    """Return [west, south, east, north] bounding box around a point."""
    west = max(lon - buffer, -180.0)
    south = max(lat - buffer, -90.0)
    east = min(lon + buffer, 180.0)
    north = min(lat + buffer, 90.0)
    return [west, south, east, north]


def make_date_range(days_back: int = DEFAULT_DAYS_BACK) -> str:
    """Return ISO date range string for STAC search."""
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    return f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"


def search_scenes(
    lat: float,
    lon: float,
    days_back: int = DEFAULT_DAYS_BACK,
    buffer: float = DEFAULT_BUFFER_DEG,
    max_cloud_cover: int = MAX_CLOUD_COVER,
) -> list:
    """Search Planetary Computer for Sentinel-2 scenes, sorted by cloud cover."""
    if not HAS_PC:
        raise ImportError(
            "Install: pip install planetary-computer pystac-client"
        )

    bbox = make_bbox(lat, lon, buffer)
    date_range = make_date_range(days_back)

    logger.info(f"Searching S2 scenes: bbox={bbox}, dates={date_range}, cloud<{max_cloud_cover}%")

    catalog = pystac_client.Client.open(
        PC_STAC_URL,
        modifier=planetary_computer.sign_inplace,
    )

    items = []
    for attempt in range(3):
        try:
            search = catalog.search(
                collections=[S2_COLLECTION],
                bbox=bbox,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": max_cloud_cover}},
                sortby=[{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            )
            items = list(search.items())[:5]
            break
        except Exception as e:
            logger.warning(f"STAC search attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2)
    logger.info(f"Found {len(items)} scenes for {date_range}")

    if not items and days_back < FALLBACK_DAYS_BACK:
        fallback_range = make_date_range(FALLBACK_DAYS_BACK)
        logger.info(f"No scenes in {days_back}d window, trying {FALLBACK_DAYS_BACK}d fallback...")
        search2 = catalog.search(
            collections=[S2_COLLECTION],
            bbox=bbox,
            datetime=fallback_range,
            query={"eo:cloud_cover": {"lt": max_cloud_cover}},
            sortby=[{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            max_items=10,
        )
        items = list(search2.items())
        if items:
            logger.info(f"Fallback-1 found {len(items)} scenes")

    # Open ocean (e.g. GPGP) has very sparse S2 coverage — all-time fallback
    if not items:
        logger.info("Still no scenes — trying all-time search with wider bbox...")
        wider_bbox = make_bbox(lat, lon, max(buffer * 2, 1.5))
        search3 = catalog.search(
            collections=[S2_COLLECTION],
            bbox=wider_bbox,
            max_items=8,
        )
        all_items = list(search3.items())
        all_items.sort(key=lambda x: x.properties.get("eo:cloud_cover", 100))
        items = all_items
        if items:
            logger.info(f"Fallback-2 (all-time wider) found {len(items)} scenes")

    return items


def _utm_epsg(lat: float, lon: float) -> int:
    """Return UTM EPSG code for given lat/lon."""
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def load_bands(
    items: list,
    lat: float,
    lon: float,
    buffer: float = DEFAULT_BUFFER_DEG,
    resolution: int = TARGET_RESOLUTION,
    max_items: int = 3,
) -> Optional[xr.DataArray]:
    """Load required bands as a lazy xarray DataArray via stackstac."""
    if not items:
        logger.warning("No scenes to load")
        return None

    items = items[:max_items]

    bbox = make_bbox(lat, lon, buffer)
    epsg = _utm_epsg(lat, lon)

    deg_per_m = 1 / 111320
    ny_est = int(buffer * 2 / (resolution * deg_per_m))
    nx_est = ny_est
    mem_gb = ny_est * nx_est * len(REQUIRED_BANDS) * len(items) * 4 / 1e9
    logger.info(f"Estimated grid: ~{ny_est}×{nx_est}px, ~{mem_gb:.1f} GB RAM for {len(items)} scenes")
    logger.info(f"Using EPSG:{epsg} (UTM), resolution={resolution}m")

    stack = stackstac.stack(
        items,
        assets=REQUIRED_BANDS,
        bounds_latlon=bbox,
        resolution=resolution,
        dtype="float64",
        fill_value=np.nan,
        rescale=False,
        epsg=epsg,
    )
    if stack.dtype != np.float32:
        stack = stack.copy(data=stack.values.astype("float32"))

    logger.info(f"Loaded stack shape: {stack.sizes}")
    return stack


def get_sentinel2_data(
    lat: float,
    lon: float,
    days_back: int = DEFAULT_DAYS_BACK,
    buffer: float = DEFAULT_BUFFER_DEG,
    max_cloud_cover: int = MAX_CLOUD_COVER,
    resolution: int = TARGET_RESOLUTION,
    max_items: int = 3,
) -> Tuple[Optional[xr.DataArray], list]:
    """Search + load Sentinel-2 data. Returns (stack, items); stack is None if no data."""
    items = search_scenes(lat, lon, days_back, buffer, max_cloud_cover)

    if not items:
        return None, []

    stack = load_bands(items, lat, lon, buffer, resolution, max_items=max_items)
    return stack, items


def get_scene_metadata(items: list) -> list[dict]:
    """Extract human-readable metadata from STAC items."""
    meta = []
    for item in items:
        meta.append({
            "id": item.id,
            "date": item.datetime.strftime("%Y-%m-%d") if item.datetime else "unknown",
            "cloud_cover": item.properties.get("eo:cloud_cover", "?"),
            "platform": item.properties.get("platform", "?"),
        })
    return meta
