"""Interactive Folium map with FDI overlay and adaptive percentile normalization."""
from __future__ import annotations

import base64
import io
from typing import Optional

import folium
import numpy as np
from folium import plugins
from matplotlib import cm, colors as mcolors
from matplotlib.colors import LinearSegmentedColormap


# navy (water) -> white (neutral) -> orange -> red (plastic)
PLASTIC_CMAP = LinearSegmentedColormap.from_list(
    "plastic",
    [(0.00, "#072b6e"),
     (0.40, "#1565c0"),
     (0.60, "#f5f5f5"),
     (0.75, "#ffb300"),
     (0.88, "#e64a19"),
     (1.00, "#b71c1c")],
)


def confidence_to_rgba(confidence_map: np.ndarray, alpha: float = 0.6) -> np.ndarray:
    """Convert confidence map (0..1) to RGBA: green->yellow->red."""
    h, w = confidence_map.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = ~np.isnan(confidence_map)
    if not valid.any():
        return rgba
    cmap = LinearSegmentedColormap.from_list(
        "confidence_gyr", ["#00c853", "#ffd600", "#d50000"],
    )
    norm = mcolors.Normalize(vmin=0.0, vmax=1.0, clip=True)
    colored = cmap(norm(confidence_map))
    rgba_float = (colored * 255).astype(np.uint8)
    rgba[valid] = rgba_float[valid]
    rgba[valid, 3] = int(alpha * 255)
    rgba[~valid, 3] = 0
    return rgba


def fdi_to_rgba(
    fdi: np.ndarray,
    plastic_mask: np.ndarray,
    cloud_mask: Optional[np.ndarray] = None,
    alpha: float = 0.82,
    percentile_lo: float = 2.0,
    percentile_hi: float = 98.0,
) -> np.ndarray:
    """Convert FDI to RGBA with adaptive p2-p98 normalization."""
    h, w = fdi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    valid = ~np.isnan(fdi)
    if not valid.any():
        return rgba

    fdi_valid = fdi[valid]
    vmin = float(np.percentile(fdi_valid, percentile_lo))
    vmax = float(np.percentile(fdi_valid, percentile_hi))
    if vmax - vmin < 1e-6:
        vmin -= 0.005
        vmax += 0.005

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    colored = PLASTIC_CMAP(norm(fdi))

    rgba_float = (colored * 255).astype(np.uint8)
    rgba[valid] = rgba_float[valid]
    rgba[valid, 3] = int(alpha * 255)
    rgba[~valid, 3] = 0

    if cloud_mask is not None:
        cloudy = (cloud_mask > 0.5) & valid
        rgba[cloudy] = [120, 120, 120, 140]

    plastic_valid = plastic_mask.astype(bool) & valid
    if plastic_valid.any():
        rgba[plastic_valid] = [220, 30, 30, 240]

    return rgba


def rgba_to_png_b64(rgba: np.ndarray) -> str:
    from PIL import Image
    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def make_folium_map(
    lat: float,
    lon: float,
    fdi: np.ndarray,
    plastic_mask: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    cloud_mask: Optional[np.ndarray] = None,
    stats: Optional[dict] = None,
    scene_dates: Optional[list] = None,
    hotspots: Optional[list] = None,
    drift_result=None,
    route_result=None,
    rgb_composite: Optional[np.ndarray] = None,
    confidence_map: Optional[np.ndarray] = None,
    hotspots_drift_corrected: Optional[list] = None,
    output_path: Optional[str] = None,
) -> folium.Map:
    """Create interactive Folium map with FDI overlay."""
    m = folium.Map(
        location=[lat, lon],
        zoom_start=9,
        tiles=None,
    )

    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="🛰 Спутник (Esri)",
        overlay=False, control=True,
    ).add_to(m)
    folium.TileLayer(
        "CartoDB dark_matter",
        name="🌑 Тёмная",
        overlay=False, control=True,
    ).add_to(m)
    folium.TileLayer(
        "OpenStreetMap",
        name="🗺 OpenStreetMap",
        overlay=False, control=True,
    ).add_to(m)

    bounds = [
        [float(lats.min()), float(lons.min())],
        [float(lats.max()), float(lons.max())],
    ]

    if rgb_composite is not None:
        from PIL import Image as PILImage
        rgb_img = PILImage.fromarray(rgb_composite, mode="RGB")
        buf = io.BytesIO()
        rgb_img.save(buf, format="PNG")
        rgb_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        folium.raster_layers.ImageOverlay(
            image=f"data:image/png;base64,{rgb_b64}",
            bounds=bounds, opacity=0.85,
            name="🌈 True-color RGB (B4/B3/B2)",
            overlay=True, control=True,
        ).add_to(m)

    rgba = fdi_to_rgba(fdi, plastic_mask, cloud_mask)
    png_b64 = rgba_to_png_b64(rgba)
    folium.raster_layers.ImageOverlay(
        image=f"data:image/png;base64,{png_b64}",
        bounds=bounds, opacity=1.0,
        name="🔥 Индекс FDI (пластик)",
        overlay=True, control=True,
    ).add_to(m)

    valid_fdi = fdi[~np.isnan(fdi)]
    if valid_fdi.size > 0:
        vmin = float(np.percentile(valid_fdi, 2))
        vmax = float(np.percentile(valid_fdi, 98))
        _add_colorbar(m, vmin, vmax)

    folium.Marker(
        [lat, lon],
        tooltip="📍 Центр поиска",
        popup=f"<b>Центр:</b> {lat:.4f}°N, {lon:.4f}°E",
        icon=folium.Icon(color="blue", icon="ship", prefix="fa"),
    ).add_to(m)

    folium.Rectangle(
        bounds=bounds, color="#29b6f6",
        fill=False, weight=1.5, dash_array="6 4",
        tooltip="Область анализа",
    ).add_to(m)

    if hotspots:
        hs_group = folium.FeatureGroup(name="📍 Горячие точки")
        for i, hs in enumerate(hotspots[:15], 1):
            r = min(6 + int(hs.get("area_km2", 0) * 5), 20)
            folium.CircleMarker(
                [hs["lat"], hs["lon"]],
                radius=r, color="#ff1744",
                fill=True, fill_color="#ff1744", fill_opacity=0.75,
                tooltip=(
                    f"<b>Точка #{i}</b><br>"
                    f"FDI: {hs.get('fdi_max',0):.5f}<br>"
                    f"Площадь: {hs.get('area_km2',0):.3f} км²<br>"
                    f"{hs['lat']:.4f}°N, {hs['lon']:.4f}°E"
                ),
            ).add_to(hs_group)
        hs_group.add_to(m)

    if drift_result is not None:
        dr = drift_result
        drift_group = folium.FeatureGroup(name="🌊 Прогноз дрейфа")

        traj = [(p[0], p[1]) for p in dr.trajectory[::2]]
        if len(traj) > 1:
            folium.PolyLine(
                traj, color="#ff9800", weight=3, opacity=0.85, dash_array="6 3",
                tooltip="Медианная траектория дрейфа",
            ).add_to(drift_group)

        for hrs, pos, unc in [
            (24, dr.positions_24h, getattr(dr, "uncertainty_km_24h", 0)),
            (48, dr.positions_48h, getattr(dr, "uncertainty_km_48h", 0)),
            (72, dr.positions_72h, getattr(dr, "uncertainty_km_72h", 0)),
        ]:
            if not pos:
                continue
            col = {24: "#ffcc02", 48: "#ff6d00", 72: "#d50000"}[hrs]

            if unc and unc > 0.5:
                folium.Circle(
                    list(pos), radius=int(unc * 1000),
                    color=col, fill=True, fill_opacity=0.1,
                    weight=1, dash_array="4 4",
                    tooltip=f"Неопределённость ±{unc:.1f} км (1σ)",
                ).add_to(drift_group)

            dist = getattr(dr, f"distance_km_{hrs}h", 0)
            folium.CircleMarker(
                list(pos), radius=9, color=col,
                fill=True, fill_opacity=0.9, weight=2,
                tooltip=(
                    f"<b>Через {hrs}ч</b><br>"
                    f"📍 {pos[0]:.4f}°N, {pos[1]:.4f}°E<br>"
                    f"📏 Смещение: {dist:.1f} км<br>"
                    f"🎯 Неопределённость: ±{unc:.1f} км"
                ),
            ).add_to(drift_group)
            folium.DivIcon(
                html=f'<div style="background:{col};color:white;padding:2px 6px;'
                     f'border-radius:4px;font-size:11px;font-weight:bold;'
                     f'box-shadow:1px 1px 3px rgba(0,0,0,0.6);white-space:nowrap">'
                     f'{hrs}ч ±{unc:.0f}км</div>',
            ).add_to(folium.Marker(list(pos)).add_to(drift_group))

        drift_group.add_to(m)

    if route_result is not None and route_result.waypoints:
        rr = route_result
        rg = folium.FeatureGroup(name="🧭 Маршрут плота")
        coords = [(lat, lon)] + [(wp.lat, wp.lon) for wp in rr.waypoints]
        drift_label = " (с учётом дрейфа)" if getattr(rr, "drift_aware", False) else ""
        folium.PolyLine(
            coords, color="#00e5ff", weight=3, opacity=0.9, dash_array="8 4",
            tooltip=f"Маршрут{drift_label}: {rr.total_distance_km:.1f} км | ETA {rr.total_eta_hours:.1f}ч",
        ).add_to(rg)
        for wp in rr.waypoints:
            dc = getattr(wp, "drift_correction_km", 0)
            drift_note = f"<br>🌊 Цель сдрейфует на {dc:.1f} км" if dc > 0.5 else ""
            folium.CircleMarker(
                [wp.lat, wp.lon], radius=6,
                color="#00e5ff", fill=True, fill_opacity=0.9,
                tooltip=(
                    f"<b>{wp.label}</b><br>"
                    f"📍 {wp.lat:.4f}°N, {wp.lon:.4f}°E<br>"
                    f"🧭 {wp.bearing_from_prev_deg:.0f}° | {wp.distance_from_prev_km:.1f} км<br>"
                    f"⏱ ETA: {wp.eta_hours:.1f}ч"
                    f"{drift_note}"
                ),
            ).add_to(rg)
        rg.add_to(m)

    if confidence_map is not None:
        conf_rgba = confidence_to_rgba(confidence_map)
        conf_b64 = rgba_to_png_b64(conf_rgba)
        folium.raster_layers.ImageOverlay(
            image=f"data:image/png;base64,{conf_b64}",
            bounds=bounds, opacity=0.9,
            name="🎯 Карта уверенности",
            overlay=True, control=True,
        ).add_to(m)

    if hotspots_drift_corrected:
        dc_group = folium.FeatureGroup(name="🔄 Скорректированные точки")
        for i, hs in enumerate(hotspots_drift_corrected[:15], 1):
            folium.CircleMarker(
                [hs["lat"], hs["lon"]],
                radius=8, color="#ff9800",
                fill=True, fill_color="#ff9800", fill_opacity=0.8,
                tooltip=(
                    f"<b>Скорр. точка #{i}</b><br>"
                    f"📍 {hs['lat']:.4f}°N, {hs['lon']:.4f}°E<br>"
                    f"🌊 Дрейф: {hs.get('drift_km', 0):.1f} км<br>"
                    f"⏱ Время: {hs.get('drift_hours', 0):.1f} ч"
                ),
            ).add_to(dc_group)
        dc_group.add_to(m)

    _add_info_panel(m, stats, scene_dates, hotspots)

    folium.LayerControl(collapsed=False).add_to(m)
    plugins.Fullscreen().add_to(m)
    plugins.MousePosition(
        position="bottomleft",
        separator=" | ",
        prefix="📍",
        lat_formatter="function(num) {return num >= 0 ? L.Util.formatNum(num, 4) + '°N' : L.Util.formatNum(-num, 4) + '°S';}",
        lng_formatter="function(num) {return num >= 0 ? L.Util.formatNum(num, 4) + '°E' : L.Util.formatNum(-num, 4) + '°W';}",
    ).add_to(m)

    if output_path:
        m.save(output_path)
    return m


def _add_colorbar(m: folium.Map, vmin: float, vmax: float):
    """Add horizontal colorbar legend."""
    stops = []
    for pct in range(0, 101, 10):
        rgba = PLASTIC_CMAP(pct / 100)
        r, g, b = int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255)
        stops.append(f"rgb({r},{g},{b}) {pct}%")
    gradient = ", ".join(stops)

    html = f"""
    <div style="
        position:fixed; bottom:20px; left:50%; transform:translateX(-50%);
        z-index:9999; background:rgba(10,22,40,0.88);
        padding:10px 18px; border-radius:10px;
        border:1px solid #1a3a5c;
        font-family:Arial,sans-serif; font-size:12px; color:white;
        box-shadow:2px 2px 8px rgba(0,0,0,0.5);
        min-width:280px;
    ">
      <div style="margin-bottom:4px;text-align:center;font-weight:bold;color:#4fc3f7">
        Индекс FDI (плавающий мусор)
      </div>
      <div style="
        height:14px; border-radius:4px;
        background: linear-gradient(to right, {gradient});
        margin-bottom:4px; border:1px solid #333;
      "></div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:#aaa">
        <span>{vmin:.4f}<br>Чистая вода</span>
        <span style="text-align:center">{(vmin+vmax)/2:.4f}<br>Зона риска</span>
        <span style="text-align:right">{vmax:.4f}<br>🔴 Пластик</span>
      </div>
      <div style="margin-top:6px;font-size:10px;color:#666;text-align:center">
        Красные маркеры = подтверждённые скопления (FDI &gt; порог + водный пиксель)
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))


def _add_info_panel(m, stats, scene_dates, hotspots):
    plastic_pct = stats.get("plastic_coverage_pct", 0) if stats else 0
    plastic_km2 = stats.get("plastic_area_km2", 0) if stats else 0
    cloud_pct = stats.get("cloud_coverage_pct", "?") if stats else "?"
    fdi_max = stats.get("fdi_max") if stats else None
    dates = (", ".join(scene_dates[:2]) if scene_dates else "—")
    hs_count = len(hotspots) if hotspots else 0
    verdict_color = "#ff5252" if plastic_pct > 0.01 else "#69f0ae"
    verdict = "⚠️ Обнаружены скопления" if plastic_pct > 0.01 else "✅ Зона чистая"

    html = f"""
    <div style="
        position:fixed; top:280px; right:12px; z-index:9998;
        background:rgba(10,22,40,0.92); padding:14px 16px;
        border-radius:10px; border:1px solid #1a3a5c;
        font-family:Arial,sans-serif; font-size:12px; color:#cdd8e3;
        box-shadow:2px 4px 12px rgba(0,0,0,0.6); max-width:200px;
    ">
      <div style="font-size:14px;font-weight:bold;color:#4fc3f7;margin-bottom:8px">
        🌊 Анализ пластика
      </div>
      <div style="color:{verdict_color};font-weight:bold;margin-bottom:8px">{verdict}</div>
      <div style="margin:3px 0">📊 Покрытие: <b>{plastic_pct:.3f}%</b></div>
      <div style="margin:3px 0">📐 Площадь: <b>{plastic_km2:.2f} км²</b></div>
      <div style="margin:3px 0">📍 Горячих точек: <b>{hs_count}</b></div>
      <div style="margin:3px 0">☁️ Облачность: <b>{cloud_pct}%</b></div>
      {"<div style='margin:3px 0'>📈 FDI макс: <b>" + f"{fdi_max:.5f}</b></div>" if fdi_max else ""}
      <hr style="border-color:#1a3a5c;margin:8px 0">
      <div style="font-size:10px;color:#666">📅 {dates}</div>
      <div style="font-size:9px;color:#444;margin-top:4px">
        FDI · Biermann 2020<br>Sentinel-2 · Planetary Computer
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))
