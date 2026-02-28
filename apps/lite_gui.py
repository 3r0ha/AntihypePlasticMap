#!/usr/bin/env python3
"""antihype Lite GUI — Bottle + Leaflet single-page app for PyInstaller packaging."""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bottle import Bottle, request, response, run as bottle_run, static_file

app = Bottle()


def _make_transparent_overlay(fdi: "np.ndarray", plastic_mask: "np.ndarray") -> str:
    """Generate a transparent PNG overlay for Leaflet as base64."""
    import io
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    h, w = fdi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    valid = ~np.isnan(fdi)
    if valid.any():
        fdi_norm = fdi.copy()
        vmin = float(np.nanpercentile(fdi, 2))
        vmax = float(np.nanpercentile(fdi, 98))
        if vmax - vmin < 1e-6:
            vmin, vmax = -0.02, 0.05
        fdi_norm = np.clip((fdi_norm - vmin) / (vmax - vmin), 0, 1)
        rgba[valid, 0] = (fdi_norm[valid] * 255).astype(np.uint8)
        rgba[valid, 2] = ((1 - fdi_norm[valid]) * 200).astype(np.uint8)
        rgba[valid, 3] = 120

    plastic = plastic_mask.astype(bool)
    rgba[plastic, 0] = 255
    rgba[plastic, 1] = 20
    rgba[plastic, 2] = 20
    rgba[plastic, 3] = 220

    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
    ax.imshow(rgba)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, transparent=True, pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

from config import PRESETS as _PRESETS_CFG

# Build dict-of-dicts format required by the Leaflet JS template
PRESETS = {key: {"lat": lat, "lon": lon, "name": name_ru}
           for key, (lat, lon, name_ru) in _PRESETS_CFG.items()}

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>antihype Lite</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>if(!window.L){document.write('<p style="color:red;padding:20px">Leaflet не загружен. Требуется интернет для карты.</p>')}</script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0a1628; color:#cdd8e3; font-family:'Segoe UI',sans-serif; }
.header { background:#0d1f35; padding:12px 20px; border-bottom:1px solid #1a3a5c; display:flex; align-items:center; gap:15px; }
.header h1 { color:#4fc3f7; font-size:20px; }
.sidebar { position:fixed; left:0; top:52px; bottom:0; width:320px; background:#0d1f35;
    border-right:1px solid #1a3a5c; padding:15px; overflow-y:auto; }
.main { margin-left:320px; margin-top:52px; padding:0; }
#map { height:calc(100vh - 52px); width:100%; }
label { display:block; color:#90caf9; font-size:12px; margin:6px 0 2px; }
input, select { width:100%; background:#112240; color:#cdd8e3; border:1px solid #1a3a5c;
    padding:6px 10px; border-radius:4px; font-size:13px; }
.btn { display:block; width:100%; background:linear-gradient(135deg,#1565c0,#0d47a1); color:white;
    border:none; padding:10px; border-radius:6px; font-size:14px; font-weight:bold; cursor:pointer; margin:10px 0; }
.btn:hover { background:#1976d2; }
.btn:disabled { opacity:0.5; cursor:wait; }
.presets { display:flex; flex-wrap:wrap; gap:4px; margin:8px 0; }
.preset-btn { background:#1a3a5c; color:#81d4fa; border:none; padding:3px 8px; border-radius:3px;
    font-size:11px; cursor:pointer; }
.preset-btn:hover { background:#1565c0; }
.stats-box { background:#112240; border:1px solid #1a3a5c; border-radius:6px; padding:10px; margin:10px 0;
    font-size:12px; display:none; }
.stats-box div { margin:2px 0; }
.stat-val { color:#4fc3f7; font-weight:bold; }
.verdict-ok { color:#69f0ae; font-weight:bold; }
.verdict-bad { color:#ff5252; font-weight:bold; }
.loading { display:none; text-align:center; padding:20px; }
.spinner { border:3px solid #1a3a5c; border-top:3px solid #4fc3f7; border-radius:50%;
    width:24px; height:24px; animation:spin 1s linear infinite; display:inline-block; }
@keyframes spin { 100% { transform:rotate(360deg); } }
.hs-list { font-size:11px; margin:5px 0; }
.hs-item { padding:3px 0; border-bottom:1px solid #0d1f35; cursor:pointer; }
.hs-item:hover { color:#4fc3f7; }
</style>
</head>
<body>
<div class="header">
    <h1>antihype Lite</h1>
    <span style="color:#90caf9;font-size:12px">Детекция морского пластика &middot; Sentinel-2</span>
</div>
<div class="sidebar">
    <label>Широта (°N)</label>
    <input type="number" id="lat" step="0.01" value="37.0">
    <label>Долгота (°E)</label>
    <input type="number" id="lon" step="0.01" value="13.0">
    <label>Период (дней)</label>
    <input type="number" id="days" value="3" min="1" max="30">
    <label>Ветер U (м/с)</label>
    <input type="number" id="wind_u" step="0.1" value="0">
    <label>Ветер V (м/с)</label>
    <input type="number" id="wind_v" step="0.1" value="0">
    <label>Пресеты</label>
    <div class="presets" id="presets"></div>
    <button class="preset-btn" onclick="getGPS()" style="background:#0d47a1">GPS</button>
    <button class="btn" id="analyzeBtn" onclick="analyze()">Анализировать</button>
    <div class="loading" id="loading">
        <div class="spinner"></div>
        <p style="margin-top:8px;color:#90caf9" id="loadingMsg">Загрузка спутниковых данных...</p>
    </div>
    <div class="stats-box" id="stats"></div>
    <div class="hs-list" id="hotspots"></div>
</div>
<div class="main">
    <div id="map"></div>
</div>
<script>
var map = L.map('map').setView([37.0, 13.0], 5);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Esri', maxZoom: 18
}).addTo(map);
var darkLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: 'CartoDB'});
var markers = L.layerGroup().addTo(map);
var imageOverlay = null;

var presets = __PRESETS_JSON__;
var presetsDiv = document.getElementById('presets');
Object.keys(presets).forEach(function(k) {
    var p = presets[k];
    var btn = document.createElement('button');
    btn.className = 'preset-btn';
    btn.textContent = p.name;
    btn.onclick = function() {
        document.getElementById('lat').value = p.lat;
        document.getElementById('lon').value = p.lon;
        map.setView([p.lat, p.lon], 7);
    };
    presetsDiv.appendChild(btn);
});

function getGPS() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(pos) {
            document.getElementById('lat').value = pos.coords.latitude.toFixed(4);
            document.getElementById('lon').value = pos.coords.longitude.toFixed(4);
            map.setView([pos.coords.latitude, pos.coords.longitude], 8);
        }, function() { alert('GPS недоступен'); });
    }
}

function analyze() {
    var lat = parseFloat(document.getElementById('lat').value);
    var lon = parseFloat(document.getElementById('lon').value);
    var days = parseInt(document.getElementById('days').value);
    var wind_u = parseFloat(document.getElementById('wind_u').value) || 0;
    var wind_v = parseFloat(document.getElementById('wind_v').value) || 0;
    var btn = document.getElementById('analyzeBtn');
    btn.disabled = true;
    document.getElementById('loading').style.display = 'block';
    document.getElementById('stats').style.display = 'none';
    document.getElementById('hotspots').innerHTML = '';
    markers.clearLayers();
    if (imageOverlay) { map.removeLayer(imageOverlay); imageOverlay = null; }

    fetch('/api/analyze?lat=' + lat + '&lon=' + lon + '&days=' + days + '&wind_u=' + wind_u + '&wind_v=' + wind_v)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            btn.disabled = false;
            document.getElementById('loading').style.display = 'none';
            if (!data.success) {
                alert('Снимки не найдены: ' + (data.warnings || []).join('; '));
                return;
            }
            showResults(data, lat, lon);
        })
        .catch(function(err) {
            btn.disabled = false;
            document.getElementById('loading').style.display = 'none';
            alert('Ошибка: ' + err);
        });
}

function showResults(data, lat, lon) {
    var s = data.stats;
    var pct = s.plastic_coverage_pct || 0;
    var verdictClass = pct > 0.01 ? 'verdict-bad' : 'verdict-ok';
    var verdictText = pct > 0.01 ? 'ОБНАРУЖЕНЫ СКОПЛЕНИЯ' : 'ЗОНА ЧИСТАЯ';

    var html = '<div class="' + verdictClass + '">' + verdictText + '</div>';
    html += '<div>Снимков: <span class="stat-val">' + data.scenes_found + '</span></div>';
    html += '<div>Пластик: <span class="stat-val">' + pct.toFixed(3) + '%</span></div>';
    html += '<div>Площадь: <span class="stat-val">' + (s.plastic_area_km2||0).toFixed(2) + ' км²</span></div>';
    html += '<div>Облачность: <span class="stat-val">' + (s.cloud_coverage_pct||'?') + '%</span></div>';
    html += '<div>FDI макс: <span class="stat-val">' + (s.fdi_max||0).toFixed(5) + '</span></div>';
    html += '<div>Уверенность: <span class="stat-val">' + ((s.confidence_mean||0)*100).toFixed(1) + '%</span></div>';
    html += '<div>Время: <span class="stat-val">' + (data.processing_time_sec || '?') + 'с</span></div>';
    document.getElementById('stats').innerHTML = html;
    document.getElementById('stats').style.display = 'block';

    if (data.png_b64 && data.bounds) {
        var b = data.bounds;
        imageOverlay = L.imageOverlay('data:image/png;base64,' + data.png_b64,
            [[b[0], b[1]], [b[2], b[3]]], {opacity: 0.75});
        imageOverlay.addTo(map);
        map.fitBounds([[b[0], b[1]], [b[2], b[3]]]);
    } else {
        map.setView([lat, lon], 8);
    }

    L.marker([lat, lon]).addTo(markers).bindPopup('Центр анализа');

    var hsDiv = document.getElementById('hotspots');
    var hsHtml = '';
    if (data.hotspots && data.hotspots.length > 0) {
        hsHtml = '<label>Горячие точки (' + data.hotspots.length + ')</label>';
        data.hotspots.slice(0, 10).forEach(function(hs, i) {
            L.circleMarker([hs.lat, hs.lon], {
                radius: Math.min(6 + hs.area_km2 * 5, 20),
                color: '#ff1744', fillColor: '#ff1744', fillOpacity: 0.7
            }).addTo(markers).bindPopup(
                '#' + (i+1) + '<br>FDI: ' + hs.fdi_max.toFixed(5) +
                '<br>' + hs.area_km2.toFixed(3) + ' км²'
            );
            hsHtml += '<div class="hs-item" onclick="map.setView([' + hs.lat + ',' + hs.lon + '],10)">' +
                '#' + (i+1) + ' ' + hs.lat.toFixed(4) + '°, ' + hs.lon.toFixed(4) + '° | ' +
                hs.fdi_max.toFixed(5) + '</div>';
        });
    }
    hsDiv.innerHTML = hsHtml;

    if (data.hotspots_drift_corrected && data.hotspots_drift_corrected.length > 0) {
        data.hotspots_drift_corrected.slice(0, 10).forEach(function(hs, i) {
            if (hs.drift_km && hs.drift_km > 0.1) {
                L.circleMarker([hs.lat, hs.lon], {
                    radius: 5, color: '#ff9800', fillColor: '#ff9800', fillOpacity: 0.7
                }).addTo(markers).bindPopup(
                    'Скорректировано #' + (i+1) + '<br>Дрейф: ' +
                    hs.drift_km.toFixed(1) + ' км / ' + hs.drift_hours.toFixed(0) + 'ч'
                );
            }
        });
    }
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    html = HTML_TEMPLATE.replace("__PRESETS_JSON__", json.dumps(PRESETS))
    response.content_type = "text/html; charset=utf-8"
    return html


@app.route("/api/analyze")
def api_analyze():
    response.content_type = "application/json"
    try:
        lat = float(request.params.get("lat", 37.0))
        lon = float(request.params.get("lon", 13.0))
        days = int(request.params.get("days", 3))
        wind_u = float(request.params.get("wind_u", 0))
        wind_v = float(request.params.get("wind_v", 0))
    except (ValueError, TypeError):
        return json.dumps({"success": False, "warnings": ["Неверные параметры"]})

    from core.processor import run_pipeline

    try:
        result = run_pipeline(lat=lat, lon=lon, days_back=days)
    except Exception as e:
        return json.dumps({"success": False, "warnings": [f"Ошибка обработки: {e}"]})

    if not result.success:
        return json.dumps({"success": False, "warnings": result.warnings})

    png_b64 = _make_transparent_overlay(result.fdi, result.plastic_mask)

    bounds = [
        float(result.lats.min()), float(result.lons.min()),
        float(result.lats.max()), float(result.lons.max()),
    ]

    resp = {
        "success": True,
        "scenes_found": result.scenes_found,
        "scene_dates": result.scene_dates,
        "stats": result.stats,
        "hotspots": result.hotspots[:15],
        "hotspots_drift_corrected": (result.hotspots_drift_corrected or [])[:15],
        "processing_time_sec": result.processing_time_sec,
        "warnings": result.warnings,
        "png_b64": png_b64,
        "bounds": bounds,
        "wind_u": wind_u,
        "wind_v": wind_v,
    }
    return json.dumps(resp, default=str)


@app.route("/health")
def health():
    response.content_type = "application/json"
    return json.dumps({"status": "ok", "service": "ecohack-lite-gui"})


def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:8090")


if __name__ == "__main__":
    print("=" * 50)
    print("  antihype Lite GUI")
    print("  http://localhost:8090")
    print("=" * 50)
    threading.Thread(target=open_browser, daemon=True).start()
    bottle_run(app, host="0.0.0.0", port=8090, quiet=False)
