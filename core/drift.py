"""
Lagrangian particle drift — ensemble simulation.

v_total = v_current + v_stokes + v_leeway
  v_stokes ~ 1.5% of current (proxy), v_leeway ~ 2.5% of 10m wind (Isobe 2014).
N=30 particles with +/-5% perturbations produce uncertainty cone.

References: van Sebille et al. (2020), Lebreton et al. (2018), Isobe et al. (2014).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.interpolate import RegularGridInterpolator

logger = logging.getLogger(__name__)

STOKES_FRACTION = 0.013    # ~1.3% of current -> Stokes drift proxy
WIND_LEEWAY = 0.025        # ~2.5% of 10m wind -> plastic leeway (Isobe 2014)
ENSEMBLE_SIZE = 30
ENSEMBLE_NOISE = 0.05      # +/-5% perturbation on currents


@dataclass
class DriftResult:
    origin_lat: float
    origin_lon: float
    hours_simulated: int

    trajectory: list[tuple[float, float]] = field(default_factory=list)

    ensemble_24h: list[tuple[float, float]] = field(default_factory=list)
    ensemble_48h: list[tuple[float, float]] = field(default_factory=list)
    ensemble_72h: list[tuple[float, float]] = field(default_factory=list)

    positions_24h: Optional[tuple[float, float]] = None
    positions_48h: Optional[tuple[float, float]] = None
    positions_72h: Optional[tuple[float, float]] = None

    uncertainty_km_24h: float = 0.0
    uncertainty_km_48h: float = 0.0
    uncertainty_km_72h: float = 0.0

    distance_km_24h: float = 0.0
    distance_km_48h: float = 0.0
    distance_km_72h: float = 0.0

    current_speed_ms: float = 0.0
    current_direction_deg: float = 0.0
    wind_speed_ms: float = 0.0
    wind_direction_deg: float = 0.0

    source: str = "unknown"
    is_synthetic: bool = True

    @property
    def final_lat(self) -> float:
        return self.trajectory[-1][0] if self.trajectory else self.origin_lat

    @property
    def final_lon(self) -> float:
        return self.trajectory[-1][1] if self.trajectory else self.origin_lon


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2)**2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _mpd_lat() -> float:
    return 111_320.0


def _mpd_lon(lat: float) -> float:
    return 111_320.0 * np.cos(np.radians(lat))


def _build_interps(arr_u, arr_v, arr_wu, arr_wv, lats, lons):
    kw = dict(method="linear", bounds_error=False, fill_value=None)

    def _prep(arr):
        a = arr.copy().astype(float)
        if np.isnan(a).any():
            m = np.nanmean(a)
            a = np.where(np.isnan(a), m if not np.isnan(m) else 0.0, a)
        return a

    return (
        RegularGridInterpolator((lats, lons), _prep(arr_u), **kw),
        RegularGridInterpolator((lats, lons), _prep(arr_v), **kw),
        RegularGridInterpolator((lats, lons), _prep(arr_wu), **kw),
        RegularGridInterpolator((lats, lons), _prep(arr_wv), **kw),
    )


def _rk4_step(lat, lon, iu, iv, iwu, iwv, dt_sec: float) -> tuple[float, float]:
    """RK4 integration: current + Stokes drift + wind leeway."""
    def vel(la, lo):
        pt = np.array([[la, lo]])
        uc = float(iu(pt))
        vc = float(iv(pt))
        wu = float(iwu(pt))
        wv = float(iwv(pt))
        us = STOKES_FRACTION * uc
        vs = STOKES_FRACTION * vc
        ul = WIND_LEEWAY * wu
        vl = WIND_LEEWAY * wv
        u_tot = uc + us + ul
        v_tot = vc + vs + vl
        return v_tot / _mpd_lat(), u_tot / _mpd_lon(la)

    k1 = vel(lat, lon)
    k2 = vel(lat + 0.5 * dt_sec * k1[0], lon + 0.5 * dt_sec * k1[1])
    k3 = vel(lat + 0.5 * dt_sec * k2[0], lon + 0.5 * dt_sec * k2[1])
    k4 = vel(lat + dt_sec * k3[0], lon + dt_sec * k3[1])

    new_lat = lat + (dt_sec / 6) * (k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
    new_lon = lon + (dt_sec / 6) * (k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
    new_lat = float(np.clip(new_lat, -89.9, 89.9))
    new_lon = float(((new_lon + 180) % 360) - 180)
    return new_lat, new_lon


def _ensemble_spread_km(positions: list[tuple[float, float]]) -> float:
    """1-sigma spatial spread of ensemble positions in km."""
    if len(positions) < 2:
        return 0.0
    lats = np.array([p[0] for p in positions])
    lons = np.array([p[1] for p in positions])
    med_lat = float(np.median(lats))
    med_lon = float(np.median(lons))
    dists = [haversine_km(med_lat, med_lon, la, lo) for la, lo in positions]
    return float(np.std(dists))


def simulate_drift(
    lat: float,
    lon: float,
    currents: dict,
    hours: int = 72,
    dt_hours: float = 0.5,
) -> DriftResult:
    """Run ensemble Lagrangian drift. Returns median trajectory + uncertainty at 24/48/72h."""
    lats_grid = currents["lats"]
    lons_grid = currents["lons"]
    u_base = currents["u"]
    v_base = currents["v"]
    wu_base = currents.get("wind_u", np.zeros_like(u_base))
    wv_base = currents.get("wind_v", np.zeros_like(v_base))

    dt_sec = dt_hours * 3600.0
    n_steps = int(hours / dt_hours)
    idx_24 = int(24 / dt_hours)
    idx_48 = int(48 / dt_hours)
    idx_72 = int(72 / dt_hours)

    rng = np.random.default_rng(7)
    all_trajectories = []

    for p in range(ENSEMBLE_SIZE):
        noise_u = 1.0 + rng.normal(0, ENSEMBLE_NOISE)
        noise_v = 1.0 + rng.normal(0, ENSEMBLE_NOISE)
        noise_wu = 1.0 + rng.normal(0, ENSEMBLE_NOISE * 0.5)
        noise_wv = 1.0 + rng.normal(0, ENSEMBLE_NOISE * 0.5)

        iu, iv, iwu, iwv = _build_interps(
            u_base * noise_u, v_base * noise_v,
            wu_base * noise_wu, wv_base * noise_wv,
            lats_grid, lons_grid,
        )

        traj = [(lat, lon)]
        cur_lat, cur_lon = lat, lon
        for _ in range(n_steps):
            cur_lat, cur_lon = _rk4_step(cur_lat, cur_lon, iu, iv, iwu, iwv, dt_sec)
            traj.append((cur_lat, cur_lon))
        all_trajectories.append(traj)

    n_traj = len(all_trajectories[0])
    median_traj = []
    for step in range(n_traj):
        step_lats = np.array([all_trajectories[p][step][0] for p in range(ENSEMBLE_SIZE)])
        step_lons = np.array([all_trajectories[p][step][1] for p in range(ENSEMBLE_SIZE)])
        median_traj.append((float(np.median(step_lats)), float(np.median(step_lons))))

    def _ensemble_at(idx):
        idx = min(idx, n_traj - 1)
        return [(all_trajectories[p][idx][0], all_trajectories[p][idx][1])
                for p in range(ENSEMBLE_SIZE)]

    ens_24 = _ensemble_at(idx_24)
    ens_48 = _ensemble_at(idx_48)
    ens_72 = _ensemble_at(idx_72)

    pos_24 = median_traj[min(idx_24, n_traj - 1)]
    pos_48 = median_traj[min(idx_48, n_traj - 1)]
    pos_72 = median_traj[min(idx_72, n_traj - 1)]

    iu0, iv0, iwu0, iwv0 = _build_interps(u_base, v_base, wu_base, wv_base, lats_grid, lons_grid)
    pt = np.array([[lat, lon]])
    uc0, vc0 = float(iu0(pt)), float(iv0(pt))
    wu0, wv0 = float(iwu0(pt)), float(iwv0(pt))

    c_speed = np.sqrt(uc0**2 + vc0**2)
    c_dir = float(np.degrees(np.arctan2(uc0, vc0))) % 360
    w_speed = np.sqrt(wu0**2 + wv0**2)
    w_dir = float(np.degrees(np.arctan2(wu0, wv0))) % 360

    return DriftResult(
        origin_lat=lat,
        origin_lon=lon,
        hours_simulated=hours,
        trajectory=median_traj[::2],
        ensemble_24h=ens_24,
        ensemble_48h=ens_48,
        ensemble_72h=ens_72,
        positions_24h=pos_24,
        positions_48h=pos_48,
        positions_72h=pos_72,
        uncertainty_km_24h=round(_ensemble_spread_km(ens_24), 1),
        uncertainty_km_48h=round(_ensemble_spread_km(ens_48), 1),
        uncertainty_km_72h=round(_ensemble_spread_km(ens_72), 1),
        distance_km_24h=round(haversine_km(lat, lon, *pos_24), 1),
        distance_km_48h=round(haversine_km(lat, lon, *pos_48), 1),
        distance_km_72h=round(haversine_km(lat, lon, *pos_72), 1),
        current_speed_ms=round(float(c_speed), 3),
        current_direction_deg=round(c_dir, 1),
        wind_speed_ms=round(float(w_speed), 1),
        wind_direction_deg=round(w_dir, 1),
        source=currents.get("source", "unknown"),
        is_synthetic=currents.get("is_synthetic", True),
    )


def simulate_drift_multi(
    hotspots: list[dict],
    currents: dict,
    hours: int = 48,
    max_hotspots: int = 5,
    **kwargs,
) -> list:
    """Simulate drift for multiple hotspots."""
    results = []
    for hs in hotspots[:max_hotspots]:
        dr = simulate_drift(hs["lat"], hs["lon"], currents, hours=hours, **kwargs)
        results.append({"hotspot": hs, "drift": dr})
    return results
