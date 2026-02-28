"""EcoHack Plastic Map — FastAPI REST endpoint."""
from __future__ import annotations

import base64
import io
import os
import sys
import asyncio
import uuid
import json
import logging
import time as _time
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from core.processor import run_pipeline
from core.currents import get_ocean_currents
from core.drift import simulate_drift
from core.route import plan_route
from config import PRESETS as _PRESETS_CFG

logger = logging.getLogger(__name__)

app = FastAPI(
    title="antihype · Plastic Map API",
    description="Automated marine plastic detection via Sentinel-2 satellite imagery",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use Redis/DB in production instead of in-memory store
_jobs: dict[str, dict] = {}
_JOBS_TTL = 3600


def _cleanup_jobs():
    now = _time.time()
    expired = [k for k, v in _jobs.items() if now - v.get("_created_ts", 0) > _JOBS_TTL]
    for k in expired:
        del _jobs[k]


class AnalyzeRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude (°N)")
    lon: float = Field(..., ge=-180, le=180, description="Longitude (°E)")
    days_back: int = Field(3, ge=1, le=30, description="Days to search back")
    buffer_deg: float = Field(0.5, ge=0.1, le=3.0, description="Search radius in degrees")
    max_cloud_cover: int = Field(85, ge=10, le=100, description="Max cloud cover %")
    include_drift: bool = Field(True, description="Include 48h drift prediction")
    include_route: bool = Field(True, description="Include route optimization")
    enable_temporal: bool = Field(False, description="Enable temporal anomaly detection")
    include_visuals: bool = Field(False, description="Include base64 PNG/HTML visuals (full mode)")
    wind_u: float = Field(0.0, description="Observed wind U component m/s (eastward)")
    wind_v: float = Field(0.0, description="Observed wind V component m/s (northward)")
    async_mode: bool = Field(False, description="Return job_id immediately, poll /analyze/{id}")
    resolution: int = Field(60, ge=10, le=500, description="Pixel resolution in meters")
    max_scenes: int = Field(5, ge=1, le=10, description="Max scenes to composite")


class DriftRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    hours: int = Field(48, ge=6, le=168)
    wind_u_ms: float = Field(0.0, description="Wind U component m/s")
    wind_v_ms: float = Field(0.0, description="Wind V component m/s")


class RouteRequest(BaseModel):
    raft_lat: float = Field(..., ge=-90, le=90)
    raft_lon: float = Field(..., ge=-180, le=180)
    hotspots: list[dict] = Field(..., description="List of {lat, lon, fdi_max, area_km2}")
    max_waypoints: int = Field(10, ge=1, le=20)


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html><body style="font-family:monospace;background:#0a1628;color:#4fc3f7;padding:40px">
    <h1>🌊 antihype · Plastic Map API</h1>
    <p>Automated marine plastic detection via Sentinel-2</p>
    <ul>
      <li><a href="/docs" style="color:#81d4fa">📚 Interactive API Docs (Swagger)</a></li>
      <li><a href="/redoc" style="color:#81d4fa">📖 ReDoc</a></li>
      <li><a href="/health" style="color:#81d4fa">❤️ Health Check</a></li>
      <li><a href="/presets" style="color:#81d4fa">🗺️ Location Presets</a></li>
    </ul>
    <h2>Quick start</h2>
    <pre style="background:#112240;padding:16px;border-radius:8px">
curl -X POST /analyze \\
     -H "Content-Type: application/json" \\
     -d '{"lat": 28.5, "lon": -145.0, "days_back": 3}'
    </pre>
    </body></html>
    """


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }


@app.get("/presets")
async def presets():
    return {
        "presets": [
            {"id": key, "name": name_ru, "lat": lat, "lon": lon}
            for key, (lat, lon, name_ru) in _PRESETS_CFG.items()
        ]
    }


def _generate_indices_png(result, req) -> str:
    """Generate 6-panel indices comparison PNG as base64."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    fdi_arr = result.fdi
    s = result.stats
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), facecolor="#07111f")
    fig.suptitle("Анализ спектральных индексов", color="white", fontsize=14, fontweight="bold")

    extent = [float(result.lons.min()), float(result.lons.max()),
              float(result.lats.min()), float(result.lats.max())]

    def _plot_index(ax, data, title, cmap, vmin=None, vmax=None, label=""):
        ax.set_facecolor("#07111f")
        if vmin is None:
            vmin = float(np.nanpercentile(data, 2))
        if vmax is None:
            vmax = float(np.nanpercentile(data, 98))
        im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax, extent=extent,
                       origin="upper", aspect="auto")
        ax.set_title(title, color="white", fontsize=10, pad=4)
        ax.tick_params(colors="#888", labelsize=7)
        for sp in ax.spines.values():
            sp.set_edgecolor("#333")
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(label, color="white", fontsize=7)
        cbar.ax.yaxis.set_tick_params(color="white")
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white", fontsize=6)

    _plot_index(axes[0, 0], fdi_arr, "FDI — Floating Debris Index\n(Biermann 2020)",
                "RdYlBu_r", -0.02, 0.05, "FDI")

    axes[0, 1].set_facecolor("#07111f")
    plastic = result.plastic_mask.astype(float)
    plastic_plot = np.where(np.isnan(fdi_arr), np.nan, plastic)
    axes[0, 1].imshow(plastic_plot,
                      cmap=mcolors.ListedColormap(["#1a4a7a", "#ff2222"]),
                      extent=extent, origin="upper", aspect="auto", vmin=0, vmax=1)
    axes[0, 1].set_title("Бинарная маска\n(синий=вода, красный=пластик)", color="white", fontsize=10, pad=4)
    axes[0, 1].tick_params(colors="#888", labelsize=7)
    for sp in axes[0, 1].spines.values():
        sp.set_edgecolor("#333")

    if result.cloud_mask is not None:
        _plot_index(axes[0, 2], result.cloud_mask,
                    "Маска облачности (SCL)\n(0=ясно, 1=облака)", "Greys", 0, 1, "Облачность")
    else:
        axes[0, 2].set_visible(False)

    axes[1, 0].set_facecolor("#112240")
    valid_fdi = fdi_arr[~np.isnan(fdi_arr)]
    if valid_fdi.size > 0:
        axes[1, 0].hist(valid_fdi, bins=80, range=(-0.05, 0.1),
                        color="#4fc3f7", alpha=0.8, edgecolor="none")
        axes[1, 0].axvline(0.005, color="#ff5252", linestyle="--", linewidth=1.5, label="Порог FDI=0.005")
        axes[1, 0].axvline(0, color="#aaa", linestyle=":", linewidth=1, alpha=0.7)
        axes[1, 0].set_title("Распределение FDI", color="white", fontsize=10)
        axes[1, 0].set_xlabel("FDI", color="#888", fontsize=8)
        axes[1, 0].set_ylabel("Пикселей", color="#888", fontsize=8)
        axes[1, 0].tick_params(colors="#888", labelsize=7)
        axes[1, 0].legend(fontsize=8, labelcolor="white", facecolor="#1a2a3a", edgecolor="#333")
        for sp in axes[1, 0].spines.values():
            sp.set_edgecolor("#333")

    axes[1, 1].set_facecolor("#112240")
    plastic_pct = s.get("plastic_coverage_pct", 0)
    cloud_pct_val = s.get("cloud_coverage_pct", 0) or 0
    water_pct = max(0, 100 - plastic_pct - float(cloud_pct_val))
    sizes = [plastic_pct, float(cloud_pct_val), water_pct]
    labels = [f"Пластик\n{plastic_pct:.3f}%", f"Облака\n{cloud_pct_val:.1f}%",
              f"Чистая вода\n{water_pct:.1f}%"]
    axes[1, 1].pie(sizes, labels=labels, autopct="%1.1f%%",
                   colors=["#ff5252", "#90a4ae", "#1565c0"],
                   explode=(0.05, 0, 0), startangle=90,
                   textprops={"color": "white", "fontsize": 7}, pctdistance=0.75)
    axes[1, 1].set_title("Состав пикселей", color="white", fontsize=10)

    axes[1, 2].set_facecolor("#112240")
    metrics = ["FDI макс", "FDI среднее", "FDI P95"]
    vals = [s.get("fdi_max") or 0, s.get("fdi_mean") or 0, s.get("fdi_p95") or 0]
    bars = axes[1, 2].bar(metrics, vals, color=["#ff5252", "#4fc3f7", "#ffb74d"],
                           alpha=0.85, edgecolor="none")
    axes[1, 2].axhline(0.005, color="#ff5252", linestyle="--", linewidth=1, label="Порог", alpha=0.7)
    axes[1, 2].set_title("Ключевые метрики FDI", color="white", fontsize=10)
    axes[1, 2].tick_params(colors="#888", labelsize=8)
    for sp in axes[1, 2].spines.values():
        sp.set_edgecolor("#333")
    for bar, val in zip(bars, vals):
        axes[1, 2].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0003,
                         f"{val:.4f}", ha="center", va="bottom", color="white", fontsize=8)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode()


def _generate_confidence_png(result) -> Optional[str]:
    """Generate confidence map PNG as base64, or None if no meaningful data."""
    if result.confidence_map is None:
        return None
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    conf = result.confidence_map
    valid = conf[~np.isnan(conf)] if hasattr(conf, '__len__') else np.array([])
    # Skip if no variation — would produce useless solid-color image
    if valid.size == 0 or np.nanmax(conf) < 0.01 or (np.nanmax(conf) - np.nanmin(valid)) < 0.005:
        return None

    extent = [float(result.lons.min()), float(result.lons.max()),
              float(result.lats.min()), float(result.lats.max())]

    fig, ax = plt.subplots(1, 1, figsize=(10, 6), facecolor="#07111f")
    ax.set_facecolor("#07111f")
    im = ax.imshow(conf, cmap="RdYlGn_r",
                    extent=extent, origin="upper", aspect="auto", vmin=0, vmax=max(float(np.nanmax(conf)), 0.1))
    ax.set_title("Карта уверенности (0=низкая, 1=высокая)", color="white", fontsize=12)
    ax.tick_params(colors="#888")
    for sp in ax.spines.values():
        sp.set_edgecolor("#333")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046)
    cbar.set_label("Уверенность", color="white")
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode()


def _generate_static_png(result, req) -> str:
    """Generate static overview PNG (4-panel) as base64."""
    from viz.plots import make_static_png
    png_bytes = make_static_png(
        fdi=result.fdi, plastic_mask=result.plastic_mask,
        lons=result.lons, lats=result.lats,
        lat=req.lat, lon=req.lon, cloud_mask=result.cloud_mask,
        stats=result.stats, scene_dates=result.scene_dates,
        confidence_map=result.confidence_map,
        hotspots=result.hotspots,
    )
    return base64.b64encode(png_bytes).decode()


def _generate_folium_html(result, req, hotspots, drift_result=None, route_result=None) -> str:
    """Generate Folium interactive map HTML as base64."""
    from viz.maps import make_folium_map
    m = make_folium_map(
        lat=req.lat, lon=req.lon,
        fdi=result.fdi, plastic_mask=result.plastic_mask,
        lons=result.lons, lats=result.lats,
        cloud_mask=result.cloud_mask, stats=result.stats,
        scene_dates=result.scene_dates,
        hotspots=hotspots,
        confidence_map=result.confidence_map,
        hotspots_drift_corrected=result.hotspots_drift_corrected,
    )
    html_bytes = m.get_root().render().encode("utf-8")
    return base64.b64encode(html_bytes).decode()


def _generate_pdf(result, req, hotspots, drift_result=None, route_result=None) -> Optional[str]:
    """Generate PDF report as base64."""
    try:
        from core.report import generate_pdf_report
        pdf_bytes = generate_pdf_report(
            lat=req.lat, lon=req.lon,
            stats=result.stats,
            fdi=result.fdi,
            plastic_mask=result.plastic_mask,
            lons_arr=result.lons,
            lats_arr=result.lats,
            cloud_mask=result.cloud_mask,
            scene_dates=result.scene_dates,
            hotspots=hotspots,
            drift_result=drift_result,
            route_result=route_result,
        )
        return base64.b64encode(pdf_bytes).decode()
    except Exception as e:
        logger.warning(f"PDF generation failed: {e}")
        return None


def _run_analysis_sync(req: AnalyzeRequest) -> dict:
    """Run the full analysis pipeline synchronously."""
    result = run_pipeline(
        lat=req.lat,
        lon=req.lon,
        days_back=req.days_back,
        buffer=req.buffer_deg,
        max_cloud_cover=req.max_cloud_cover,
        enable_temporal=req.enable_temporal,
        resolution=req.resolution,
        max_scenes=req.max_scenes,
    )

    response: dict = {
        "success": result.success,
        "lat": req.lat,
        "lon": req.lon,
        "scenes_found": result.scenes_found,
        "scene_dates": result.scene_dates,
        "stats": result.stats,
        "processing_time_sec": result.processing_time_sec,
        "warnings": result.warnings,
    }

    response["hotspots_drift_corrected"] = result.hotspots_drift_corrected
    response["fdi_threshold_used"] = result.fdi_threshold_used
    response["glint_pixels"] = result.stats.get("glint_pixels", 0)
    response["confidence_mean"] = result.stats.get("confidence_mean", 0)

    if not result.success:
        return response

    response["hotspots"] = result.hotspots
    hotspots = result.hotspots

    drift_obj = None
    route_obj = None
    if req.include_drift and hotspots:
        currents = get_ocean_currents(req.lat, req.lon, buffer=2.0)
        drift_results = []
        for top_hs in hotspots[:3]:
            drift = simulate_drift(top_hs["lat"], top_hs["lon"], currents, hours=72)
            if drift_obj is None:
                drift_obj = drift
            drift_results.append({
                "hotspot": {"lat": top_hs["lat"], "lon": top_hs["lon"]},
                "origin": {"lat": drift.origin_lat, "lon": drift.origin_lon},
                "position_24h": {"lat": drift.positions_24h[0], "lon": drift.positions_24h[1]} if drift.positions_24h else None,
                "position_48h": {"lat": drift.positions_48h[0], "lon": drift.positions_48h[1]} if drift.positions_48h else None,
                "distance_km_24h": drift.distance_km_24h,
                "distance_km_48h": drift.distance_km_48h,
                "current_speed_ms": drift.current_speed_ms,
                "current_direction_deg": drift.current_direction_deg,
                "current_source": drift.source,
                "is_synthetic": drift.is_synthetic,
            })
        response["drift"] = drift_results

    if req.include_route and hotspots:
        route = plan_route(req.lat, req.lon, hotspots)
        route_obj = route
        response["route"] = {
            "n_waypoints": len(route.waypoints),
            "total_distance_km": route.total_distance_km,
            "total_eta_hours": route.total_eta_hours,
            "total_eta_days": route.total_eta_days,
            "waypoints": [
                {
                    "label": wp.label,
                    "lat": wp.lat,
                    "lon": wp.lon,
                    "bearing_deg": wp.bearing_from_prev_deg,
                    "distance_km": wp.distance_from_prev_km,
                    "eta_hours": wp.eta_hours,
                    "fdi_max": wp.fdi_max,
                    "area_km2": wp.area_km2,
                }
                for wp in route.waypoints
            ],
        }

    if req.include_visuals:
        # Export plastic mask clusters as GeoJSON when mask and coordinates are available
        if (
            getattr(result, "plastic_mask", None) is not None
            and getattr(result, "lats", None) is not None
            and getattr(result, "lons", None) is not None
        ):
            try:
                from core.indices import mask_to_geojson
                import numpy as np

                mask_arr = result.plastic_mask
                if hasattr(mask_arr, "values"):
                    mask_arr = mask_arr.values
                mask_arr = mask_arr.astype(bool)

                lats_arr = result.lats if isinstance(result.lats, np.ndarray) else np.array(result.lats)
                lons_arr = result.lons if isinstance(result.lons, np.ndarray) else np.array(result.lons)

                response["plastic_geojson"] = mask_to_geojson(mask_arr, lats_arr, lons_arr)
            except Exception as e:
                logger.warning(f"GeoJSON mask export failed: {e}")
                response["plastic_geojson"] = None

        try:
            response["visuals"] = {
                "indices_png": _generate_indices_png(result, req),
                "static_png": _generate_static_png(result, req),
                "folium_html": _generate_folium_html(result, req, hotspots),
                "pdf": _generate_pdf(result, req, hotspots, drift_obj, route_obj),
            }
        except Exception as e:
            logger.warning(f"Visual generation failed: {e}")
            response["visuals"] = None

    return response


@app.post("/analyze")
async def analyze(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    _cleanup_jobs()

    if req.async_mode:
        job_id = str(uuid.uuid4())[:8]
        _jobs[job_id] = {"status": "pending", "created_at": datetime.utcnow().isoformat(), "_created_ts": _time.time()}

        def run_bg():
            try:
                _jobs[job_id]["status"] = "running"
                result = _run_analysis_sync(req)
                _jobs[job_id].update({"status": "done", "result": result})
            except Exception as e:
                _jobs[job_id].update({"status": "error", "error": str(e)})

        background_tasks.add_task(run_bg)
        return {"job_id": job_id, "status": "pending", "poll_url": f"/analyze/{job_id}"}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _run_analysis_sync, req)
        return result
    except Exception as e:
        logger.exception("Analyze sync error")
        return {
            "success": False,
            "scenes_found": 0,
            "hotspots": [],
            "stats": {},
            "warnings": [f"Ошибка обработки: {e}"],
            "scene_dates": [],
        }


@app.get("/analyze/{job_id}")
async def get_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _jobs[job_id]


@app.post("/drift")
async def drift_endpoint(req: DriftRequest):
    currents = get_ocean_currents(req.lat, req.lon, buffer=2.0)
    drift = simulate_drift(
        req.lat, req.lon, currents,
        hours=req.hours,
    )
    return {
        "origin": {"lat": drift.origin_lat, "lon": drift.origin_lon},
        "trajectory": [{"lat": p[0], "lon": p[1]} for p in drift.trajectory[::3]],
        "position_24h": {"lat": drift.positions_24h[0], "lon": drift.positions_24h[1]} if drift.positions_24h else None,
        "position_48h": {"lat": drift.positions_48h[0], "lon": drift.positions_48h[1]} if drift.positions_48h else None,
        "position_72h": {"lat": drift.positions_72h[0], "lon": drift.positions_72h[1]} if drift.positions_72h else None,
        "distance_km_24h": drift.distance_km_24h,
        "distance_km_48h": drift.distance_km_48h,
        "current_speed_ms": drift.current_speed_ms,
        "current_direction_deg": drift.current_direction_deg,
        "current_source": drift.source,
        "is_synthetic": drift.is_synthetic,
    }


@app.post("/route")
async def route_endpoint(req: RouteRequest):
    route = plan_route(
        req.raft_lat, req.raft_lon,
        req.hotspots,
        max_hotspots=req.max_waypoints,
    )
    return {
        "n_waypoints": len(route.waypoints),
        "total_distance_km": route.total_distance_km,
        "total_eta_hours": route.total_eta_hours,
        "total_eta_days": route.total_eta_days,
        "waypoints": [
            {
                "label": wp.label,
                "lat": wp.lat,
                "lon": wp.lon,
                "bearing_deg": wp.bearing_from_prev_deg,
                "distance_km": wp.distance_from_prev_km,
                "eta_hours": wp.eta_hours,
                "fdi_max": wp.fdi_max,
                "area_km2": wp.area_km2,
            }
            for wp in route.waypoints
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
