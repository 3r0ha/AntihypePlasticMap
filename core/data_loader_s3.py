"""
Alternative data sources for open ocean plastic detection.

Sentinel-2 was designed for land — it misses most of the open ocean.
These sources provide global daily ocean coverage:

  Sentinel-3 OLCI/SLSTR — ESA, 300m resolution, designed for ocean, daily
  NASA MODIS Terra/Aqua — 250-500m, daily global, via NASA Earthdata/LAADS
  Copernicus CDSE        — new ESA hub, all Sentinel missions, free account

For the hackathon demo: Sentinel-3 via Planetary Computer is easiest.
For production: Copernicus Marine Service (CMEMS) has ready-made products.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


# ── Sentinel-3 OLCI via Planetary Computer ───────────────────────────────

def search_sentinel3(
    lat: float,
    lon: float,
    days_back: int = 7,
    buffer: float = 1.0,
) -> list:
    """
    Search Sentinel-3 OLCI WFR L2 scenes on Planetary Computer.
    300m resolution, full-spectrum, daily global coverage.

    Sentinel-3 OLCI indices for plastic:
      - FAI adapted (bands Oa10/Oa17/Oa21)
      - Oa08/Oa10/Oa12 — similar logic to FDI
    """
    try:
        import pystac_client
        import planetary_computer
        from config import PC_STAC_URL

        catalog = pystac_client.Client.open(
            PC_STAC_URL,
            modifier=planetary_computer.sign_inplace,
        )

        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days_back)
        date_range = f"{start_dt.strftime('%Y-%m-%d')}/{end_dt.strftime('%Y-%m-%d')}"
        bbox = [lon - buffer, lat - buffer, lon + buffer, lat + buffer]

        # Try Sentinel-3 OLCI Water Full Resolution
        for collection in ["sentinel-3-olci-wfr-l2-netcdf", "sentinel-3-slstr-lst-l2-netcdf"]:
            search = catalog.search(
                collections=[collection],
                bbox=bbox,
                datetime=date_range,
                max_items=5,
            )
            items = list(search.items())
            if items:
                logger.info(f"S3 {collection}: {len(items)} scenes found")
                return items, collection

        return [], None

    except Exception as e:
        logger.warning(f"Sentinel-3 search failed: {e}")
        return [], None


def compute_fdi_s3(bands: dict) -> Optional[np.ndarray]:
    """
    Compute adapted FAI/FDI for Sentinel-3 OLCI.

    OLCI band equivalents to S2 for FDI:
      Oa10 (681nm) ≈ Red
      Oa17 (865nm) ≈ NIR (B8A)
      Oa21 (1020nm) — no SWIR in OLCI

    Since OLCI has no SWIR, use AFAI (Alternative Floating Algae Index):
      AFAI = Oa17 - [Oa10 + (Oa21 - Oa10) * (865-681)/(1020-681)]

    Note: This primarily detects Sargassum + floating debris,
    not pure plastic. Use as secondary indicator.
    """
    try:
        oa10 = bands.get("Oa10")  # 681nm
        oa17 = bands.get("Oa17")  # 865nm
        oa21 = bands.get("Oa21")  # 1020nm

        if oa10 is None or oa17 is None or oa21 is None:
            return None

        lam10, lam17, lam21 = 681.0, 865.0, 1020.0
        slope = (lam17 - lam10) / (lam21 - lam10)
        oa17_prime = oa10 + (oa21 - oa10) * slope

        afai = oa17 - oa17_prime
        return afai.astype("float32")

    except Exception as e:
        logger.warning(f"S3 AFAI computation failed: {e}")
        return None


# ── NASA MODIS via NASA Earthdata ─────────────────────────────────────────

def search_modis_earthdata(
    lat: float,
    lon: float,
    days_back: int = 3,
) -> Optional[dict]:
    """
    Fetch MODIS Terra MOD09GQ (250m daily surface reflectance)
    via NASA LAADS DAAC public API.

    No registration needed for basic access.
    Returns URL list for downloading.

    Bands for NDVI/FAI approximation:
      Band 1: 620-670nm (Red)
      Band 2: 841-876nm (NIR)
    Note: No SWIR in 250m product — use for NDVI water mask only.
    """
    try:
        import requests

        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days_back)

        # NASA LAADS DAAC CMR API
        url = "https://cmr.earthdata.nasa.gov/search/granules.json"
        params = {
            "short_name": "MOD09GQ",
            "version": "006",
            "temporal": f"{start_dt.strftime('%Y-%m-%d')},{end_dt.strftime('%Y-%m-%d')}",
            "bounding_box": f"{lon-1},{lat-1},{lon+1},{lat+1}",
            "page_size": 5,
        }
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            return None

        data = resp.json()
        granules = data.get("feed", {}).get("entry", [])
        if not granules:
            return None

        urls = []
        for g in granules:
            for link in g.get("links", []):
                if link.get("rel", "").endswith("/data#") and link.get("href", "").endswith(".hdf"):
                    urls.append(link["href"])

        return {"granules": granules, "urls": urls, "count": len(granules)}

    except Exception as e:
        logger.warning(f"MODIS LAADS search failed: {e}")
        return None


# ── Copernicus Data Space Ecosystem (CDSE) ────────────────────────────────

def search_copernicus_cdse(
    lat: float,
    lon: float,
    days_back: int = 7,
    buffer: float = 0.5,
    collection: str = "SENTINEL-2",
) -> list[dict]:
    """
    Search Copernicus Data Space Ecosystem (CDSE) — new Copernicus hub.
    Free registration: https://dataspace.copernicus.eu/

    Supports: Sentinel-1, 2, 3, 5P, Landsat

    Returns list of scene metadata dicts (not STAC items).
    Full download requires authentication.
    """
    try:
        import requests

        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days_back)

        # CDSE OData API
        url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        bbox_wkt = (
            f"POLYGON(({lon-buffer} {lat-buffer},"
            f"{lon+buffer} {lat-buffer},"
            f"{lon+buffer} {lat+buffer},"
            f"{lon-buffer} {lat+buffer},"
            f"{lon-buffer} {lat-buffer}))"
        )

        params = {
            "$filter": (
                f"Collection/Name eq '{collection}' and "
                f"OData.CSC.Intersects(area=geography'SRID=4326;{bbox_wkt}') and "
                f"ContentDate/Start gt {start_dt.strftime('%Y-%m-%dT00:00:00.000Z')} and "
                f"ContentDate/Start lt {end_dt.strftime('%Y-%m-%dT23:59:59.000Z')}"
            ),
            "$orderby": "ContentDate/Start desc",
            "$top": 10,
        }

        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            logger.warning(f"CDSE API error: {resp.status_code}")
            return []

        data = resp.json()
        items = data.get("value", [])
        logger.info(f"CDSE {collection}: {len(items)} scenes found")

        return [
            {
                "id": it.get("Id"),
                "name": it.get("Name"),
                "date": it.get("ContentDate", {}).get("Start", "")[:10],
                "size_mb": round(it.get("ContentLength", 0) / 1e6, 1),
                "origin": "Copernicus CDSE",
            }
            for it in items
        ]

    except Exception as e:
        logger.warning(f"CDSE search failed: {e}")
        return []


# ── Multi-source summary ──────────────────────────────────────────────────

def get_available_data_sources(lat: float, lon: float, days_back: int = 7) -> dict:
    """
    Check all available data sources for given coordinates.
    Returns summary dict for display in UI.
    """
    from core.data_loader import search_scenes

    result = {}

    # Sentinel-2 (Planetary Computer)
    s2_items = search_scenes(lat, lon, days_back=days_back, max_cloud_cover=100)
    result["sentinel2"] = {
        "name": "Sentinel-2 L2A",
        "resolution": "20m",
        "revisit": "5 дней",
        "coverage": "Суша + прибрежные воды",
        "scenes_found": len(s2_items),
        "note": "Основной источник для FDI",
        "source": "Microsoft Planetary Computer",
    }

    # Sentinel-3 (Planetary Computer)
    s3_items, s3_col = search_sentinel3(lat, lon, days_back=days_back)
    result["sentinel3"] = {
        "name": "Sentinel-3 OLCI",
        "resolution": "300m",
        "revisit": "~2 дня",
        "coverage": "Глобальная, включая открытый океан",
        "scenes_found": len(s3_items),
        "note": "Рекомендован для открытого океана",
        "source": "Microsoft Planetary Computer",
        "collection": s3_col,
    }

    # Copernicus CDSE
    cdse_items = search_copernicus_cdse(lat, lon, days_back=days_back)
    result["cdse_s2"] = {
        "name": "Sentinel-2 (CDSE)",
        "resolution": "20m",
        "revisit": "5 дней",
        "coverage": "Суша + прибрежные воды",
        "scenes_found": len(cdse_items),
        "note": "Метаданные доступны. Скачивание: нужен аккаунт dataspace.copernicus.eu",
        "source": "Copernicus Data Space Ecosystem",
    }

    return result
