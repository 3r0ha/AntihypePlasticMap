"""
Spectral indices for floating plastic/debris detection.

Primary index: FDI (Biermann et al. 2020) — FDI = R(NIR) - R'(NIR)
Also: FAI (Hu 2009), PI (Kikaki 2020), NDVI, NDWI (McFeeters 1996).

Detection mask layers: SCL water + NDWI > 0, land exclusion, sun glint filter,
FDI > adaptive threshold (Otsu/mean+3sigma), NDVI band, NIR/SWIR caps,
morphological opening.

References:
  Biermann et al. (2020) Sci. Rep. 10:5364
  Hu (2009) JGR Oceans 114:C10012
  Kikaki et al. (2020) Remote Sensing 12:2648
  Hedley et al. (2005) — Sun glint correction
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import xarray as xr

from config import (
    FDI_ABSOLUTE_FLOOR,
    FDI_PLASTIC_THRESHOLD,
    MIN_CLUSTER_PIXELS,
    NDVI_MAX_THRESHOLD,
    NDVI_MIN_THRESHOLD,
    NDWI_WATER_THRESHOLD,
    NIR_MAX_REFLECTANCE,
    PI_PLASTIC_THRESHOLD,
    SCL_LAND_VALUES,
    SCL_WATER_VALUE,
    SWIR_MAX_REFLECTANCE,
    WAVELENGTHS,
)

logger = logging.getLogger(__name__)

# Central wavelengths (nm)
LAM = {
    "B03": 560.0,
    "B04": 665.0,
    "B06": 740.0,
    "B08": 842.0,
    "B8A": 865.0,
    "B11": 1610.0,
    "B12": 2190.0,
}


def compute_fdi(composite: xr.DataArray) -> xr.DataArray:
    """
    Floating Debris Index (Biermann et al. 2020).
    FDI = R(NIR) - R'(NIR), where R' is B06->B11 baseline interpolation.
    Uses B8A (865nm); falls back to B08 (842nm).
    """
    b06 = composite.sel(band="B06").astype("float32")
    b11 = composite.sel(band="B11").astype("float32")

    if "B8A" in composite.band.values:
        nir = composite.sel(band="B8A").astype("float32")
        nir_band = "B8A (865nm)"
        lam_nir = LAM["B8A"]
    else:
        nir = composite.sel(band="B08").astype("float32")
        nir_band = "B08 (842nm, fallback)"
        lam_nir = LAM["B08"]
        logger.warning(
            "B8A unavailable — using B08 as FDI NIR band. "
            "FDI accuracy may be reduced (842nm vs 865nm)."
        )

    lam6, lam11 = LAM["B06"], LAM["B11"]
    slope = (lam_nir - lam6) / (lam11 - lam6)
    nir_prime = b06 + (b11 - b06) * slope

    fdi = nir - nir_prime
    fdi.name = "FDI"
    fdi.attrs.update({
        "long_name": "Floating Debris Index",
        "description": "Positive = floating material above spectral baseline",
        "reference": "Biermann et al. 2020 doi:10.1038/s41598-020-62298-z",
        "bands_used": f"B06 (740nm), {nir_band}, B11 (1610nm)",
    })
    return fdi


def compute_fai(composite: xr.DataArray) -> xr.DataArray:
    """Floating Algae Index (Hu 2009)."""
    b04 = composite.sel(band="B04").astype("float32")
    b08 = composite.sel(band="B08").astype("float32")
    b11 = composite.sel(band="B11").astype("float32")

    lam4, lam8, lam11 = LAM["B04"], LAM["B08"], LAM["B11"]
    slope = (lam8 - lam4) / (lam11 - lam4)
    b08_prime = b04 + (b11 - b04) * slope

    fai = b08 - b08_prime
    fai.name = "FAI"
    fai.attrs.update({
        "long_name": "Floating Algae / Debris Index",
        "reference": "Hu (2009) JGR Oceans 114:C10012",
        "bands_used": "B04 (665nm), B08 (842nm), B11 (1610nm)",
    })
    return fai


def compute_pi(composite: xr.DataArray) -> xr.DataArray:
    """Plastic Index (Kikaki et al. 2020)."""
    b04 = composite.sel(band="B04").astype("float32")
    b08 = composite.sel(band="B08").astype("float32")

    pi = b08 / (b08 + b04 + 1e-10)
    pi.name = "PI"
    pi.attrs.update({
        "long_name": "Plastic Index",
        "reference": "Kikaki et al. 2020 Remote Sensing 12:2648",
        "bands_used": "B04 (665nm), B08 (842nm)",
    })
    return pi


def compute_ndvi(composite: xr.DataArray) -> xr.DataArray:
    """NDVI — separates bio-debris (algae/Sargassum) from inorganic plastic."""
    b04 = composite.sel(band="B04").astype("float32")
    b08 = composite.sel(band="B08").astype("float32")

    ndvi = (b08 - b04) / (b08 + b04 + 1e-10)
    ndvi.name = "NDVI"
    ndvi.attrs.update({
        "long_name": "Normalized Difference Vegetation Index",
        "description": "High NDVI (>0.3) = likely algae/seaweed, not plastic",
        "bands_used": "B04 (665nm), B08 (842nm)",
    })
    return ndvi


def compute_ndwi(composite: xr.DataArray) -> xr.DataArray:
    """NDWI — water mask. Positive = water pixel."""
    b03 = composite.sel(band="B03").astype("float32")
    b08 = composite.sel(band="B08").astype("float32")

    ndwi = (b03 - b08) / (b03 + b08 + 1e-10)
    ndwi.name = "NDWI"
    ndwi.attrs.update({
        "long_name": "Normalized Difference Water Index",
        "description": "Positive = water. Suppresses land false positives.",
        "bands_used": "B03 (560nm), B08 (842nm)",
    })
    return ndwi


def compute_ndwi_swir(composite: xr.DataArray) -> xr.DataArray:
    """
    Modified NDWI using SWIR-2 (MNDWI, Xu 2006).
    MNDWI = (B03 - B12) / (B03 + B12).
    More effective than classic NDWI at suppressing built-up / debris false positives.
    """
    b03 = composite.sel(band="B03").astype("float32")
    b12 = composite.sel(band="B12").astype("float32")

    mndwi = (b03 - b12) / (b03 + b12 + 1e-10)
    mndwi.name = "MNDWI"
    mndwi.attrs.update({
        "long_name": "Modified Normalized Difference Water Index (SWIR-2)",
        "description": "Positive = water. Uses B12 (2190nm) for stronger land/debris suppression.",
        "reference": "Xu (2006) Int. J. Remote Sensing 27:3025-3033",
        "bands_used": "B03 (560nm), B12 (2190nm)",
    })
    return mndwi


def compute_glint_mask(composite: xr.DataArray) -> xr.DataArray:
    """
    Detect sun glint: specular reflection with ~flat spectral response.
    Glint if B08 > 0.04, B08/B03 in [0.7, 1.4], B11 < 0.02.
    Reference: Hedley et al. (2005).
    """
    b03 = composite.sel(band="B03").astype("float32")
    b08 = composite.sel(band="B08").astype("float32")
    b11 = composite.sel(band="B11").astype("float32")

    ratio = b08 / (b03 + 1e-10)

    glint = (
        (b08 > 0.04) &
        (ratio > 0.7) &
        (ratio < 1.4) &
        (b11 < 0.02)
    )

    glint.name = "glint_mask"
    glint.attrs["long_name"] = "Sun glint mask (True = glint, exclude)"
    return glint


def _otsu_threshold(values: np.ndarray) -> float:
    """Otsu's method on continuous FDI values (256-bin histogram)."""
    vmin, vmax = float(np.min(values)), float(np.max(values))
    if vmax - vmin < 1e-10:
        return vmax

    n_bins = 256
    hist, bin_edges = np.histogram(values, bins=n_bins, range=(vmin, vmax))
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    total = hist.sum()
    if total == 0:
        return vmax

    w0 = np.cumsum(hist).astype(float)
    w1 = total - w0
    mu0_cum = np.cumsum(hist * bin_centers)

    mu0 = mu0_cum / (w0 + 1e-10)
    mu_total = mu0_cum[-1] / total
    mu1 = (mu0_cum[-1] - mu0_cum) / (w1 + 1e-10)

    sigma_b = w0 * w1 * (mu0 - mu1) ** 2

    idx = np.argmax(sigma_b)
    return float(bin_centers[idx])


def compute_adaptive_fdi_threshold(
    fdi: xr.DataArray,
    water_mask: xr.DataArray,
    n_sigma: float = 3.0,
    floor: float = FDI_PLASTIC_THRESHOLD,
) -> float:
    """
    Hybrid adaptive threshold: max(Otsu, mean+3sigma, floor).
    Operates on FDI values over confirmed water pixels.
    """
    fdi_water = fdi.where(water_mask).values.ravel()
    fdi_water = fdi_water[~np.isnan(fdi_water)]

    if fdi_water.size < 100:
        logger.warning(
            f"Too few water pixels ({fdi_water.size}) for adaptive threshold, "
            f"using fixed threshold {floor}"
        )
        return floor

    mean_fdi = float(np.mean(fdi_water))
    std_fdi = float(np.std(fdi_water))
    sigma_threshold = mean_fdi + n_sigma * std_fdi

    positive_fdi = fdi_water[fdi_water > 0]
    if positive_fdi.size > 50:
        otsu = _otsu_threshold(positive_fdi)
        logger.info(f"Otsu threshold on positive FDI: {otsu:.5f}")
    else:
        otsu = 0.0
        logger.info("Not enough positive FDI pixels for Otsu, skipping")

    threshold = max(sigma_threshold, otsu, floor, FDI_ABSOLUTE_FLOOR)

    logger.info(
        f"Adaptive FDI threshold: mean={mean_fdi:.5f}, std={std_fdi:.5f}, "
        f"mean+3σ={sigma_threshold:.5f}, otsu={otsu:.5f}, final={threshold:.5f}"
    )
    return threshold


def compute_confidence_map(
    fdi: xr.DataArray,
    plastic_mask: xr.DataArray,
    fdi_threshold: float,
) -> np.ndarray:
    """
    Sub-pixel confidence: linearly scales from 0 at threshold to 1 at p99 FDI.
    At 60m resolution a pixel covers 3600m2, so confidence approximates debris fraction.
    """
    fdi_vals = fdi.values if hasattr(fdi, "values") else fdi
    mask_vals = plastic_mask.values if hasattr(plastic_mask, "values") else plastic_mask
    mask_vals = mask_vals.astype(bool)

    confidence = np.zeros_like(fdi_vals, dtype=np.float32)

    if not mask_vals.any():
        return confidence

    plastic_fdi = fdi_vals[mask_vals]
    fdi_p99 = float(np.nanpercentile(plastic_fdi, 99))

    if fdi_p99 <= fdi_threshold:
        confidence[mask_vals] = 0.5
        return confidence

    raw = (fdi_vals - fdi_threshold) / (fdi_p99 - fdi_threshold)
    confidence[mask_vals] = np.clip(raw[mask_vals], 0.0, 1.0).astype(np.float32)

    return confidence


def compute_plastic_mask(
    fdi: xr.DataArray,
    ndwi: xr.DataArray,
    composite: xr.DataArray,
    ndvi: Optional[xr.DataArray] = None,
    pi: Optional[xr.DataArray] = None,
    fdi_threshold: Optional[float] = None,
) -> tuple[xr.DataArray, float]:
    """
    Multi-layer plastic detection mask.
    Layers: water confirmation, land exclusion, glint exclusion,
    adaptive FDI threshold, PI, NDVI filter, NIR/SWIR caps.
    """
    has_scl = "SCL" in composite.band.values
    if has_scl:
        scl = composite.sel(band="SCL")
        scl_water = (scl == SCL_WATER_VALUE)
        scl_land = xr.zeros_like(scl, dtype=bool)
        for val in SCL_LAND_VALUES:
            scl_land = scl_land | (scl == val)
        water_mask = (scl_water | (ndwi > NDWI_WATER_THRESHOLD)) & (~scl_land)
    else:
        water_mask = ndwi > NDWI_WATER_THRESHOLD

    glint_mask = compute_glint_mask(composite)
    water_mask = water_mask & (~glint_mask)

    if fdi_threshold is None:
        fdi_threshold = compute_adaptive_fdi_threshold(fdi, water_mask)

    mask = water_mask & (fdi > fdi_threshold) & (fdi > FDI_ABSOLUTE_FLOOR)

    if pi is not None:
        mask = mask & (pi > PI_PLASTIC_THRESHOLD)

    if ndvi is not None:
        mask = mask & (ndvi > NDVI_MIN_THRESHOLD) & (ndvi < NDVI_MAX_THRESHOLD)

    if "B08" in composite.band.values:
        b08 = composite.sel(band="B08").astype("float32")
        mask = mask & (b08 < NIR_MAX_REFLECTANCE)

    if "B11" in composite.band.values:
        b11 = composite.sel(band="B11").astype("float32")
        mask = mask & (b11 < SWIR_MAX_REFLECTANCE)

    if "B12" in composite.band.values:
        b12 = composite.sel(band="B12").astype("float32")
        mask = mask & (b12 < SWIR_MAX_REFLECTANCE)

    mask.name = "plastic_mask"
    mask.attrs["long_name"] = (
        "Plastic detection mask "
        "(Otsu_FDI + SCL_water + NDWI + glint + NDVI + NIR_cap + SWIR_cap)"
    )
    return mask, fdi_threshold


def apply_morphological_filter(mask: np.ndarray, min_pixels: int = MIN_CLUSTER_PIXELS) -> np.ndarray:
    """Remove connected components smaller than min_pixels."""
    from scipy.ndimage import binary_opening, label, sum as ndi_sum

    if mask.sum() == 0:
        return mask

    # Skip morphological opening — at 100m resolution, debris can be 1-2 pixels
    labeled, n_features = label(mask)
    if n_features == 0:
        return mask

    component_sizes = ndi_sum(mask, labeled, range(1, n_features + 1))
    small_labels = set(
        i + 1 for i, size in enumerate(component_sizes) if size < min_pixels
    )
    result = mask.copy()
    if small_labels:
        remove_mask = np.isin(labeled, list(small_labels))
        result[remove_mask] = False

    return result


def compute_sargassum_mask(
    fai: xr.DataArray,
    ndvi: xr.DataArray,
    ndwi: xr.DataArray,
    fai_threshold: float = 0.002,
    ndvi_threshold: float = 0.05,
) -> xr.DataArray:
    """Mask for Sargassum/bio-debris (high FAI + high NDVI over water)."""
    mask = (fai > fai_threshold) & (ndvi > ndvi_threshold) & (ndwi > 0.0)
    mask.name = "sargassum_mask"
    mask.attrs["long_name"] = "Sargassum / bio-debris mask"
    return mask


def compute_all_indices(composite: xr.DataArray) -> dict[str, xr.DataArray]:
    """Compute all spectral indices and plastic mask. Returns dict of DataArrays."""
    fdi = compute_fdi(composite)
    ndwi = compute_ndwi(composite)

    result: dict[str, xr.DataArray] = {"fdi": fdi, "ndwi": ndwi}

    has_b04 = "B04" in composite.band.values
    ndvi = None
    pi = None

    if has_b04:
        ndvi = compute_ndvi(composite)
        fai = compute_fai(composite)
        pi = compute_pi(composite)
        result.update({"ndvi": ndvi, "fai": fai, "pi": pi})
        result["sargassum_mask"] = compute_sargassum_mask(fai, ndvi, ndwi)

    if "B12" in composite.band.values:
        mndwi = compute_ndwi_swir(composite)
        result["mndwi"] = mndwi

    result["glint_mask"] = compute_glint_mask(composite)

    plastic_mask, fdi_threshold = compute_plastic_mask(
        fdi, ndwi, composite, ndvi=ndvi, pi=pi,
    )
    result["plastic_mask"] = plastic_mask
    result["fdi_threshold"] = fdi_threshold

    return result


def compute_stats(
    fdi: xr.DataArray,
    plastic_mask: xr.DataArray,
    cloud_mask: Optional[xr.DataArray] = None,
    pixel_size_m: float = 20.0,
    confidence_map: Optional[np.ndarray] = None,
) -> dict:
    """Compute statistics including area in km2 and confidence."""
    fdi_vals = fdi.values if hasattr(fdi, "values") else fdi
    plastic_vals = plastic_mask.values if hasattr(plastic_mask, "values") else plastic_mask
    plastic_vals = plastic_vals.astype(bool)

    valid = ~np.isnan(fdi_vals)
    total_valid = int(valid.sum())
    plastic_pixels = int(plastic_vals[valid].sum()) if total_valid > 0 else 0
    plastic_pct = 100.0 * plastic_pixels / total_valid if total_valid > 0 else 0.0

    pixel_area_km2 = (pixel_size_m / 1000.0) ** 2
    total_area_km2 = total_valid * pixel_area_km2
    plastic_area_km2 = plastic_pixels * pixel_area_km2

    stats = {
        "total_valid_pixels": total_valid,
        "plastic_pixels": plastic_pixels,
        "plastic_coverage_pct": round(plastic_pct, 4),
        "total_area_km2": round(total_area_km2, 1),
        "plastic_area_km2": round(plastic_area_km2, 3),
        "fdi_max": float(np.nanmax(fdi_vals)) if total_valid else None,
        "fdi_mean": float(np.nanmean(fdi_vals)) if total_valid else None,
        "fdi_median": float(np.nanmedian(fdi_vals)) if total_valid else None,
        "fdi_p95": float(np.nanpercentile(fdi_vals, 95)) if total_valid else None,
        "fdi_p99": float(np.nanpercentile(fdi_vals, 99)) if total_valid else None,
    }

    if cloud_mask is not None:
        cloud_vals = cloud_mask.values if hasattr(cloud_mask, "values") else cloud_mask
        cloud_pct = 100.0 * float(np.nanmean(cloud_vals))
        stats["cloud_coverage_pct"] = round(cloud_pct, 1)

    if confidence_map is not None and plastic_pixels > 0:
        conf_plastic = confidence_map[plastic_vals]
        stats["confidence_mean"] = round(float(np.mean(conf_plastic)), 3)
        stats["confidence_max"] = round(float(np.max(conf_plastic)), 3)
        stats["confidence_min"] = round(float(np.min(conf_plastic)), 3)

    return stats


def find_hotspots(
    fdi: np.ndarray,
    plastic_mask: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    top_n: int = 10,
    min_cluster_pixels: int = MIN_CLUSTER_PIXELS,
    confidence_map: Optional[np.ndarray] = None,
) -> list[dict]:
    """Find top-N plastic hotspot locations by FDI, with optional confidence."""
    from scipy.ndimage import label

    if plastic_mask.sum() == 0:
        return []

    labeled, n_features = label(plastic_mask)
    if n_features == 0:
        return []

    hotspots = []
    pixel_size_deg = lons[1] - lons[0] if len(lons) > 1 else 60.0 / 111320
    center_lat = float(np.mean(lats))
    pixel_size_m_est = abs(float(pixel_size_deg)) * 111320 * math.cos(math.radians(center_lat))
    pixel_area_km2 = (pixel_size_m_est / 1000.0) ** 2

    for i in range(1, n_features + 1):
        component = labeled == i
        n_pixels = int(component.sum())
        if n_pixels < min_cluster_pixels:
            continue

        ys, xs = np.where(component)
        cy = int(np.mean(ys))
        cx = int(np.mean(xs))

        fdi_vals = fdi[component]
        valid = ~np.isnan(fdi_vals)
        if not valid.any():
            continue

        max_fdi = float(np.nanmax(fdi_vals))

        if cy < len(lats) and cx < len(lons):
            center_lat = float(lats[cy])
            center_lon = float(lons[cx])
        else:
            continue

        hotspot = {
            "lat": round(center_lat, 5),
            "lon": round(center_lon, 5),
            "fdi_max": round(max_fdi, 5),
            "area_km2": round(n_pixels * pixel_area_km2, 3),
            "n_pixels": n_pixels,
        }

        if confidence_map is not None:
            conf_vals = confidence_map[component]
            hotspot["confidence_mean"] = round(float(np.mean(conf_vals)), 3)
            hotspot["confidence_max"] = round(float(np.max(conf_vals)), 3)

        hotspots.append(hotspot)

    hotspots.sort(key=lambda x: x["fdi_max"], reverse=True)
    return hotspots[:top_n]


def mask_to_geojson(
    plastic_mask: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
) -> dict:
    """
    Convert a binary plastic mask to a GeoJSON FeatureCollection.

    Uses scipy.ndimage.label to identify connected components.  For each
    component a rectangular Polygon bounding-box feature is created with
    properties: area_pixels, center_lat, center_lon.

    Parameters
    ----------
    plastic_mask : np.ndarray
        2-D boolean array (rows = lat axis, cols = lon axis).
    lats : np.ndarray
        1-D array of latitude values corresponding to mask rows.
    lons : np.ndarray
        1-D array of longitude values corresponding to mask columns.

    Returns
    -------
    dict
        GeoJSON FeatureCollection dict.
    """
    from scipy.ndimage import label

    features: list[dict] = []

    if plastic_mask.sum() == 0:
        return {"type": "FeatureCollection", "features": features}

    labeled, n_features = label(plastic_mask)
    if n_features == 0:
        return {"type": "FeatureCollection", "features": features}

    for i in range(1, n_features + 1):
        component = labeled == i
        ys, xs = np.where(component)
        if ys.size == 0:
            continue

        area_pixels = int(ys.size)

        # Bounding-box indices
        y_min, y_max = int(ys.min()), int(ys.max())
        x_min, x_max = int(xs.min()), int(xs.max())

        # Guard against out-of-range indices
        if y_max >= len(lats) or x_max >= len(lons):
            continue

        # Coordinate extents — add half-pixel padding so the polygon
        # covers the full pixel footprint.
        lat_step = abs(float(lats[1] - lats[0])) / 2.0 if len(lats) > 1 else 0.0
        lon_step = abs(float(lons[1] - lons[0])) / 2.0 if len(lons) > 1 else 0.0

        lat_north = float(lats[y_min]) + lat_step
        lat_south = float(lats[y_max]) - lat_step
        lon_west = float(lons[x_min]) - lon_step
        lon_east = float(lons[x_max]) + lon_step

        # Closed ring (GeoJSON requires first == last)
        ring = [
            [lon_west, lat_north],
            [lon_east, lat_north],
            [lon_east, lat_south],
            [lon_west, lat_south],
            [lon_west, lat_north],
        ]

        cy = int(np.mean(ys))
        cx = int(np.mean(xs))
        center_lat = float(lats[cy]) if cy < len(lats) else float(np.mean([lat_north, lat_south]))
        center_lon = float(lons[cx]) if cx < len(lons) else float(np.mean([lon_west, lon_east]))

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring],
            },
            "properties": {
                "area_pixels": area_pixels,
                "center_lat": round(center_lat, 6),
                "center_lon": round(center_lon, 6),
            },
        }
        features.append(feature)

    logger.info(f"mask_to_geojson: {len(features)} polygon features from {n_features} components")
    return {"type": "FeatureCollection", "features": features}
