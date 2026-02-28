#!/usr/bin/env python3
"""antihype Lite Web — ultra-lightweight server for satellite internet (<50KB pages)."""
from __future__ import annotations

import base64
import html as html_mod
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bottle import Bottle, request, response, run as bottle_run

app = Bottle()


def _make_light_png(fdi, plastic_mask, lat, lon) -> str:
    """Single-panel FDI+plastic JPEG, <40KB at 72dpi."""
    import io
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    step = max(1, max(fdi.shape) // 150)
    fdi = fdi[::step, ::step]
    plastic_mask = plastic_mask[::step, ::step]
    fig, ax = plt.subplots(figsize=(4, 3.5), facecolor="#0a1628", dpi=72)
    ax.set_facecolor("#0a1628")

    valid = ~np.isnan(fdi)
    if valid.any():
        vmin = float(np.nanpercentile(fdi, 2))
        vmax = float(np.nanpercentile(fdi, 98))
        if vmax - vmin < 1e-6:
            vmin, vmax = -0.02, 0.05
    else:
        vmin, vmax = -0.02, 0.05

    cmap = mcolors.LinearSegmentedColormap.from_list("fdi", [
        "#072b6e", "#1565c0", "#f5f5f5", "#ffb300", "#e64a19", "#b71c1c"])
    ax.imshow(fdi, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

    pm = plastic_mask.astype(bool)
    if pm.any():
        overlay = np.where(pm, 1.0, np.nan)
        ax.imshow(overlay, cmap=mcolors.ListedColormap(["#ff1744"]),
                  alpha=0.8, aspect="auto")

    ax.set_title(f"FDI — {lat:.2f}°N, {lon:.2f}°E", color="white", fontsize=11)
    ax.axis("off")
    plt.tight_layout(pad=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="jpeg", dpi=72, facecolor=fig.get_facecolor(),
                pil_kwargs={"quality": 60})
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

_cache = {}
_CACHE_TTL = 600

from config import PRESETS

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0a1628; color: #cdd8e3; font-family: 'Courier New', monospace; padding: 20px; }
h1 { color: #4fc3f7; margin-bottom: 10px; }
h2 { color: #81d4fa; margin: 15px 0 8px; }
.container { max-width: 900px; margin: 0 auto; }
input, select, button { background: #112240; color: #cdd8e3; border: 1px solid #1a3a5c;
    padding: 8px 12px; border-radius: 6px; font-family: inherit; font-size: 14px; }
button { background: #1565c0; color: white; cursor: pointer; font-weight: bold; }
button:hover { background: #1976d2; }
.form-row { display: flex; gap: 10px; margin: 8px 0; flex-wrap: wrap; }
.presets { display: flex; gap: 6px; flex-wrap: wrap; margin: 10px 0; }
.presets a { background: #1a3a5c; color: #81d4fa; padding: 4px 10px; border-radius: 4px;
    text-decoration: none; font-size: 12px; }
.presets a:hover { background: #1565c0; }
.stats { background: #112240; border: 1px solid #1a3a5c; border-radius: 8px; padding: 12px; margin: 10px 0; }
.stats div { margin: 4px 0; }
.stat-val { color: #4fc3f7; font-weight: bold; }
.verdict-ok { color: #69f0ae; font-weight: bold; font-size: 18px; }
.verdict-bad { color: #ff5252; font-weight: bold; font-size: 18px; }
img { max-width: 100%; border-radius: 8px; margin: 10px 0; border: 1px solid #1a3a5c; }
.warn { color: #ffb74d; }
.footer { color: #455a64; font-size: 11px; margin-top: 20px; text-align: center; }
"""


def _html_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style></head>
<body><div class="container">{body}</div></body></html>"""


@app.route("/")
def index():
    preset_links = ""
    for pid, (plat, plon, pname) in PRESETS.items():
        preset_links += f'<a href="/analyze?lat={plat}&lon={plon}&days=3">{pname}</a>\n'

    gps_btn = ('<button type="button" onclick="navigator.geolocation&&navigator.geolocation'
               ".getCurrentPosition(function(p){"
               "document.querySelector('[name=lat]').value=p.coords.latitude.toFixed(4);"
               "document.querySelector('[name=lon]').value=p.coords.longitude.toFixed(4)"
               '})">'
               'GPS</button>')

    body = f"""
    <h1>antihype Lite</h1>
    <p>Детекция морского пластика &middot; Sentinel-2 FDI</p>
    <h2>Координаты</h2>
    <form action="/analyze" method="get">
      <div class="form-row">
        <label>Широта: <input type="number" name="lat" step="0.01" value="37.0" required></label>
        <label>Долгота: <input type="number" name="lon" step="0.01" value="13.0" required></label>
        <label>Дней: <input type="number" name="days" value="3" min="1" max="30"></label>
        <button type="submit">Анализировать</button>
        {gps_btn}
      </div>
    </form>
    <h2>Пресеты</h2>
    <div class="presets">{preset_links}</div>
    <div class="footer">antihype &middot; Sentinel-2 &middot; Microsoft Planetary Computer</div>
    """
    return _html_page("antihype Lite", body)


@app.route("/analyze")
def analyze():
    try:
        lat = float(request.params.get("lat", 37.0))
        lon = float(request.params.get("lon", 13.0))
        days = int(request.params.get("days", 3))
    except (ValueError, TypeError):
        return _html_page("Ошибка", "<h1>Ошибка</h1><p>Неверные параметры</p>")

    from core.processor import run_pipeline

    cache_key = (round(lat, 2), round(lon, 2), days)
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _CACHE_TTL:
        result = cached[0]
        elapsed = 0.0
    else:
        t0 = time.time()
        try:
            result = run_pipeline(lat=lat, lon=lon, days_back=days)
        except Exception as e:
            body = f"""<h1>antihype Lite</h1>
            <h2>Ошибка обработки</h2>
            <p class="warn">{html_mod.escape(str(e))}</p>
            <p><a href="/">Назад</a></p>"""
            return _html_page("Ошибка", body)
        elapsed = time.time() - t0
        _cache[cache_key] = (result, time.time())
        if len(_cache) > 20:
            oldest_key = min(_cache, key=lambda k: _cache[k][1])
            del _cache[oldest_key]

    if not result.success:
        warnings_html = "".join(f'<p class="warn">{html_mod.escape(w)}</p>' for w in result.warnings)
        body = f"""<h1>antihype Lite</h1>
        <h2>Снимки не найдены</h2>
        {warnings_html}
        <p>Попробуйте увеличить период или выбрать другой район.</p>
        <p><a href="/">Назад</a></p>"""
        return _html_page("Нет данных", body)

    stats = result.stats
    plastic_pct = stats.get("plastic_coverage_pct", 0)
    verdict_class = "verdict-bad" if plastic_pct > 0.01 else "verdict-ok"
    verdict_text = "ОБНАРУЖЕНЫ СКОПЛЕНИЯ" if plastic_pct > 0.01 else "ЗОНА ЧИСТАЯ"

    png_b64 = _make_light_png(result.fdi, result.plastic_mask, lat, lon)

    warnings_html = "".join(f'<p class="warn">{html_mod.escape(w)}</p>' for w in result.warnings)

    hs_html = ""
    if result.hotspots:
        hs_html = "<h2>Горячие точки</h2><div class='stats'>"
        for i, hs in enumerate(result.hotspots[:8], 1):
            hs_html += (f"<div>#{i}: {hs['lat']:.4f}°N, {hs['lon']:.4f}°E | "
                       f"FDI: {hs['fdi_max']:.5f} | {hs['area_km2']:.3f} км²</div>")
        hs_html += "</div>"

    body = f"""
    <h1>antihype Lite</h1>
    <p><a href="/">← Новый анализ</a></p>
    <div class="{verdict_class}">{verdict_text}</div>
    <div class="stats">
      <div>Координаты: <span class="stat-val">{lat:.4f}°N, {lon:.4f}°E</span></div>
      <div>Снимков: <span class="stat-val">{result.scenes_found}</span> ({', '.join(result.scene_dates)})</div>
      <div>Покрытие пластиком: <span class="stat-val">{plastic_pct:.3f}%</span></div>
      <div>Площадь: <span class="stat-val">{stats.get('plastic_area_km2', 0):.2f} км²</span></div>
      <div>Облачность: <span class="stat-val">{stats.get('cloud_coverage_pct', '?')}%</span></div>
      <div>FDI макс: <span class="stat-val">{stats.get('fdi_max', 0):.5f}</span></div>
      <div>FDI порог: <span class="stat-val">{stats.get('fdi_threshold_used', '?')}</span></div>
      <div>Уверенность: <span class="stat-val">{stats.get('confidence_mean', 0):.1%}</span></div>
      <div>Glint: <span class="stat-val">{stats.get('glint_pixels', 0)}</span></div>
      <div>Горячих точек: <span class="stat-val">{len(result.hotspots)}</span></div>
      <div>Время: <span class="stat-val">{elapsed:.1f}с</span></div>
    </div>
    {warnings_html}
    <h2>Карта</h2>
    <img src="data:image/jpeg;base64,{png_b64}" alt="Карта FDI">
    {hs_html}
    <div class="footer">antihype &middot; Sentinel-2 FDI &middot; {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
    """
    response.content_type = "text/html; charset=utf-8"
    return _html_page(f"antihype: {lat:.2f}°N {lon:.2f}°E", body)


@app.route("/health")
def health():
    response.content_type = "application/json"
    return json.dumps({"status": "ok", "timestamp": datetime.utcnow().isoformat(), "service": "ecohack-lite"})


if __name__ == "__main__":
    print("antihype Lite Web: http://localhost:8088")
    bottle_run(app, host="0.0.0.0", port=8088, quiet=False)
