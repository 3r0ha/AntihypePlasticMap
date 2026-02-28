"""
Cloud masking for Sentinel-2 using Scene Classification Layer (SCL).

SCL classes masked: 3 (cloud shadows), 8 (cloud medium), 9 (cloud high),
10 (thin cirrus), 11 (snow/ice).
"""
from __future__ import annotations

import numpy as np
import xarray as xr

from config import SCL_CLOUD_VALUES


def apply_cloud_mask(stack: xr.DataArray) -> tuple[xr.DataArray, xr.DataArray]:
    """Apply SCL-based cloud mask. Returns (masked_stack, cloud_mask_da)."""
    scl = stack.sel(band="SCL")

    cloud_mask = xr.DataArray(
        np.isin(scl.values, list(SCL_CLOUD_VALUES)),
        dims=scl.dims, coords=scl.coords,
    )

    mask_expanded = cloud_mask.expand_dims(dim={"band": stack.band}, axis=1)
    masked_stack = stack.where(~mask_expanded)

    return masked_stack, cloud_mask


def cloud_cover_fraction(cloud_mask: xr.DataArray) -> xr.DataArray:
    """Cloud cover fraction per time step, values 0.0-1.0."""
    return cloud_mask.mean(dim=["y", "x"])


def select_least_cloudy(
    stack: xr.DataArray,
    cloud_mask: xr.DataArray,
    max_fraction: float = 0.5,
) -> tuple[xr.DataArray, xr.DataArray]:
    """Filter time steps below max_fraction cloud cover; keep best if none pass."""
    fractions = cloud_cover_fraction(cloud_mask).compute()
    good = fractions[fractions <= max_fraction].time.values

    if len(good) > 0:
        return stack.sel(time=good), cloud_mask.sel(time=good)
    else:
        best_time = fractions.idxmin(dim="time").values
        return stack.sel(time=[best_time]), cloud_mask.sel(time=[best_time])


def make_composite(
    masked_stack: xr.DataArray,
    cloud_mask: xr.DataArray,
) -> xr.DataArray:
    """Median composite over time, ignoring NaN (cloudy) pixels. Returns (band, y, x)."""
    composite = masked_stack.median(dim="time", skipna=True)
    return composite
