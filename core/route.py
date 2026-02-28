"""
Drift-aware route planner for raft through plastic hotspots.

Routes to predicted future positions: both raft and plastic drift with current,
but raft has ~2 knots active propulsion. Uses greedy + 2-opt optimization.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.interpolate import RegularGridInterpolator

logger = logging.getLogger(__name__)

RAFT_SPEED_THROUGH_WATER_MS = 1.0    # ~2 knots
RAFT_SPEED_KMH = RAFT_SPEED_THROUGH_WATER_MS * 3.6


@dataclass
class Waypoint:
    lat: float
    lon: float
    label: str
    fdi_max: float = 0.0
    area_km2: float = 0.0
    distance_from_prev_km: float = 0.0
    bearing_from_prev_deg: float = 0.0
    eta_hours: float = 0.0
    drift_correction_km: float = 0.0
    priority: int = 0


@dataclass
class RouteResult:
    start_lat: float
    start_lon: float
    waypoints: list[Waypoint] = field(default_factory=list)
    total_distance_km: float = 0.0
    total_eta_hours: float = 0.0
    total_eta_days: float = 0.0
    n_hotspots: int = 0
    drift_aware: bool = False


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2)**2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dlam = np.radians(lon2 - lon1)
    x = np.sin(dlam) * np.cos(phi2)
    y = np.cos(phi1)*np.sin(phi2) - np.sin(phi1)*np.cos(phi2)*np.cos(dlam)
    return (np.degrees(np.arctan2(x, y)) + 360) % 360


def _get_current_at(lat, lon, currents: dict) -> tuple[float, float]:
    """Interpolate u, v current at a point."""
    try:
        kw = dict(method="linear", bounds_error=False, fill_value=0.0)
        u_arr = currents["u"].astype(float)
        v_arr = currents["v"].astype(float)
        u_arr = np.where(np.isnan(u_arr), 0.0, u_arr)
        v_arr = np.where(np.isnan(v_arr), 0.0, v_arr)
        iu = RegularGridInterpolator((currents["lats"], currents["lons"]), u_arr, **kw)
        iv = RegularGridInterpolator((currents["lats"], currents["lons"]), v_arr, **kw)
        pt = np.array([[lat, lon]])
        return float(iu(pt)), float(iv(pt))
    except Exception:
        return 0.0, 0.0


def _drift_position(lat, lon, currents, hours: float) -> tuple[float, float]:
    """Forward Euler estimate of passive particle position after `hours`."""
    if hours <= 0 or currents is None:
        return lat, lon

    dt_h = 1.0
    cur_lat, cur_lon = lat, lon

    wind_u = currents.get("wind_u", np.zeros_like(currents["u"]))
    wind_v = currents.get("wind_v", np.zeros_like(currents["v"]))
    from .currents import PLASTIC_WIND_LEEWAY

    kw = dict(method="linear", bounds_error=False, fill_value=None)

    def _prep(arr):
        a = arr.copy().astype(float)
        m = np.nanmean(a)
        return np.where(np.isnan(a), m if not np.isnan(m) else 0.0, a)

    from scipy.interpolate import RegularGridInterpolator as RGI
    iu = RGI((currents["lats"], currents["lons"]), _prep(currents["u"]), **kw)
    iv = RGI((currents["lats"], currents["lons"]), _prep(currents["v"]), **kw)
    iwu = RGI((currents["lats"], currents["lons"]), _prep(wind_u), **kw)
    iwv = RGI((currents["lats"], currents["lons"]), _prep(wind_v), **kw)

    n = int(hours / dt_h)
    dt_sec = dt_h * 3600.0
    mpd_lat = 111_320.0

    for _ in range(n):
        pt = np.array([[cur_lat, cur_lon]])
        uc = float(iu(pt)); vc = float(iv(pt))
        wu = float(iwu(pt)); wv = float(iwv(pt))
        u_tot = uc + PLASTIC_WIND_LEEWAY * wu
        v_tot = vc + PLASTIC_WIND_LEEWAY * wv
        mpd_lon = mpd_lat * np.cos(np.radians(cur_lat))
        cur_lat = float(np.clip(cur_lat + v_tot * dt_sec / mpd_lat, -89.9, 89.9))
        cur_lon = float(((cur_lon + u_tot * dt_sec / mpd_lon + 180) % 360) - 180)

    return cur_lat, cur_lon


def plan_route(
    start_lat: float,
    start_lon: float,
    hotspots: list[dict],
    currents: Optional[dict] = None,
    max_hotspots: int = 12,
    raft_speed_kmh: float = RAFT_SPEED_KMH,
) -> RouteResult:
    """Plan optimal interception route through drifting plastic hotspots."""
    result = RouteResult(start_lat=start_lat, start_lon=start_lon)
    if not hotspots:
        return result

    scored = sorted(
        hotspots,
        key=lambda h: h.get("fdi_max", 0) * (1 + h.get("area_km2", 0)),
        reverse=True,
    )
    selected = scored[:max_hotspots]
    result.n_hotspots = len(selected)
    result.drift_aware = currents is not None

    waypoints: list[Waypoint] = []
    cumulative_dist = 0.0
    cumulative_h = 0.0
    prev_lat, prev_lon = start_lat, start_lon
    remaining = list(selected)
    rank = 1

    while remaining:
        best_idx = None
        best_dist = float("inf")
        best_target_lat = None
        best_target_lon = None
        best_drift_km = 0.0

        for i, hs in enumerate(remaining):
            d_static = haversine_km(prev_lat, prev_lon, hs["lat"], hs["lon"])

            if currents is not None and raft_speed_kmh > 0:
                eta_h = (cumulative_h + d_static / raft_speed_kmh)
                tgt_lat, tgt_lon = _drift_position(
                    hs["lat"], hs["lon"], currents, hours=eta_h
                )
                d = haversine_km(prev_lat, prev_lon, tgt_lat, tgt_lon)
                drift_km = haversine_km(hs["lat"], hs["lon"], tgt_lat, tgt_lon)
            else:
                tgt_lat, tgt_lon = hs["lat"], hs["lon"]
                d = d_static
                drift_km = 0.0

            if d < best_dist:
                best_dist = d
                best_idx = i
                best_target_lat = tgt_lat
                best_target_lon = tgt_lon
                best_drift_km = drift_km

        hs = remaining.pop(best_idx)
        travel_h = best_dist / raft_speed_kmh if raft_speed_kmh > 0 else 0

        if currents is not None:
            uc, vc = _get_current_at(prev_lat, prev_lon, currents)
            bear_rad = np.radians(bearing_deg(prev_lat, prev_lon, best_target_lat, best_target_lon))
            current_along_kmh = (uc * np.sin(bear_rad) + vc * np.cos(bear_rad)) * 3.6
            effective_speed = max(raft_speed_kmh + current_along_kmh, 0.5)
            travel_h = best_dist / effective_speed

        cumulative_dist += best_dist
        cumulative_h += travel_h

        wp = Waypoint(
            lat=round(best_target_lat, 5),
            lon=round(best_target_lon, 5),
            label=f"WP-{rank:02d}",
            fdi_max=hs.get("fdi_max", 0.0),
            area_km2=hs.get("area_km2", 0.0),
            distance_from_prev_km=round(best_dist, 2),
            bearing_from_prev_deg=round(
                bearing_deg(prev_lat, prev_lon, best_target_lat, best_target_lon), 1
            ),
            eta_hours=round(cumulative_h, 1),
            drift_correction_km=round(best_drift_km, 2),
            priority=rank,
        )
        waypoints.append(wp)
        prev_lat, prev_lon = best_target_lat, best_target_lon
        rank += 1

    if len(waypoints) >= 4:
        waypoints = _two_opt_waypoints(start_lat, start_lon, waypoints)

    result.waypoints = waypoints
    result.total_distance_km = round(sum(w.distance_from_prev_km for w in waypoints), 2)
    result.total_eta_hours = round(waypoints[-1].eta_hours if waypoints else 0, 1)
    result.total_eta_days = round(result.total_eta_hours / 24, 1)
    return result


def _two_opt_waypoints(
    start_lat: float,
    start_lon: float,
    waypoints: list[Waypoint],
) -> list[Waypoint]:
    """2-opt improvement: swap edge pairs to reduce total distance."""
    if len(waypoints) < 4:
        return waypoints

    pts = [(start_lat, start_lon)] + [(w.lat, w.lon) for w in waypoints]

    def route_len(route):
        return sum(haversine_km(*route[i], *route[i+1]) for i in range(len(route)-1))

    best = pts[:]
    best_len = route_len(best)
    improved = True
    iters = 0

    while improved and iters < 100:
        improved = False
        iters += 1
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                candidate = best[:i] + best[i:j+1][::-1] + best[j+1:]
                clen = route_len(candidate)
                if clen < best_len - 0.01:
                    best = candidate
                    best_len = clen
                    improved = True

    result = []
    cumulative_dist = 0.0
    cumulative_h = 0.0
    prev_lat, prev_lon = start_lat, start_lon
    wp_by_pos = {(w.lat, w.lon): w for w in waypoints}

    for i, (la, lo) in enumerate(best[1:], start=1):
        orig_wp = wp_by_pos.get((la, lo))
        dist = haversine_km(prev_lat, prev_lon, la, lo)
        travel_h = dist / RAFT_SPEED_KMH if RAFT_SPEED_KMH > 0 else 0
        cumulative_dist += dist
        cumulative_h += travel_h

        wp = Waypoint(
            lat=la, lon=lo,
            label=f"WP-{i:02d}",
            fdi_max=orig_wp.fdi_max if orig_wp else 0.0,
            area_km2=orig_wp.area_km2 if orig_wp else 0.0,
            distance_from_prev_km=round(dist, 2),
            bearing_from_prev_deg=round(bearing_deg(prev_lat, prev_lon, la, lo), 1),
            eta_hours=round(cumulative_h, 1),
            drift_correction_km=orig_wp.drift_correction_km if orig_wp else 0.0,
            priority=i,
        )
        result.append(wp)
        prev_lat, prev_lon = la, lo

    return result


def route_to_geojson(route: RouteResult) -> dict:
    features = []
    coords = [[route.start_lon, route.start_lat]]
    for wp in route.waypoints:
        coords.append([wp.lon, wp.lat])

    features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "total_distance_km": route.total_distance_km,
            "total_eta_hours": route.total_eta_hours,
            "drift_aware": route.drift_aware,
        },
    })
    features.append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [route.start_lon, route.start_lat]},
        "properties": {"type": "start"},
    })
    for wp in route.waypoints:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [wp.lon, wp.lat]},
            "properties": {
                "label": wp.label,
                "fdi_max": wp.fdi_max,
                "area_km2": wp.area_km2,
                "bearing_deg": wp.bearing_from_prev_deg,
                "distance_km": wp.distance_from_prev_km,
                "eta_hours": wp.eta_hours,
                "drift_correction_km": wp.drift_correction_km,
            },
        })
    return {"type": "FeatureCollection", "features": features}
