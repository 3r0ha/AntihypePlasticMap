"""EcoHack Plastic Map — Streamlit Web App."""
from __future__ import annotations

import io
import json
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="antihype · Карта пластика",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #07111f; }
  [data-testid="stSidebar"] { background: #0d1f35; border-right: 1px solid #1a3a5c; }
  [data-testid="stSidebar"] * { color: #cdd8e3 !important; }
  .main .block-container { padding-top: 1.2rem; }

  h1 { color: #4fc3f7 !important; font-size: 1.8rem !important; }
  h2 { color: #81d4fa !important; }
  h3 { color: #b3e5fc !important; }
  p, li, label { color: #cdd8e3 !important; }

  [data-testid="metric-container"] {
    background: #112240 !important;
    border: 1px solid #1a3a5c !important;
    border-radius: 10px !important;
    padding: 12px !important;
  }
  [data-testid="metric-container"] label { color: #90caf9 !important; font-size: 0.78rem !important; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #ffffff !important; font-size: 1.5rem !important; font-weight: bold !important;
  }

  .stButton > button {
    background: linear-gradient(135deg, #1565c0, #0d47a1) !important;
    color: white !important; border: none !important;
    border-radius: 8px !important; font-weight: bold !important;
    width: 100% !important; padding: 0.55rem 1rem !important;
  }
  .stButton > button:hover { background: #1976d2 !important; transform: translateY(-1px); }

  [data-testid="stTabs"] button { color: #90caf9 !important; font-weight: 500 !important; }
  [data-testid="stTabs"] button[aria-selected="true"] {
    color: #4fc3f7 !important; border-bottom: 2px solid #4fc3f7 !important;
  }

  [data-testid="stTable"] { background: #112240 !important; }
  thead tr th { background: #1565c0 !important; color: white !important; }

  [data-testid="stAlert"] { background: #112240 !important; border-color: #1565c0 !important; }

  hr { border-color: #1a3a5c !important; }

  [data-testid="stExpander"] { background: #0d1f35 !important; border: 1px solid #1a3a5c !important; }
</style>
""", unsafe_allow_html=True)

from config import DEFAULT_DAYS_BACK as _DEFAULT_DAYS_BACK
from config import PRESETS as _PRESETS_CFG

# Build display-name -> (lat, lon) mapping from canonical config for the selectbox
PRESETS = {name_ru: (lat, lon) for _, (lat, lon, name_ru) in _PRESETS_CFG.items()}

for key, val in [
    ("result", None),
    ("currents", None),
    ("drift_result", None),
    ("route_result", None),
    ("hotspots", None),
    ("timeseries_result", None),
    ("lat", 28.5),
    ("lon", -145.0),
]:
    if key not in st.session_state:
        st.session_state[key] = val


with st.sidebar:
    st.markdown("## ⚙️ Параметры")

    preset_name = st.selectbox("Район", ["— Ввести вручную —"] + list(PRESETS.keys()))
    if preset_name != "— Ввести вручную —":
        st.session_state.lat, st.session_state.lon = PRESETS[preset_name]

    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Широта °N", -90.0, 90.0, float(st.session_state.lat), 0.1, format="%.4f")
    with col2:
        lon = st.number_input("Долгота °E", -180.0, 180.0, float(st.session_state.lon), 0.1, format="%.4f")

    st.session_state.lat = lat
    st.session_state.lon = lon

    st.markdown("---")
    days_back = st.slider("Период поиска (дней)", 1, 30, _DEFAULT_DAYS_BACK)
    buffer = st.slider("Радиус поиска (°)", 0.1, 2.0, 0.5, 0.1)
    max_cloud = st.slider("Макс. облачность %", 10, 100, 85, 5)

    st.markdown("---")

    st.markdown("**Разрешение обработки:**")
    resolution = st.select_slider(
        "Разрешение (м)",
        options=[60, 100, 200, 300],
        value=200,
        help="200м — быстро (<1мин). 100м — детальнее. 60м — макс качество (медленно)."
    )
    max_scenes = st.slider("Макс. снимков", 1, 5, 1,
                           help="Меньше = быстрее. 1 снимок обычно достаточно")

    st.markdown("**Дополнительно:**")
    include_drift = st.checkbox("Прогноз дрейфа (48ч)", value=False,
                                help="Добавляет ~15с. Включите после первого анализа")
    include_route = st.checkbox("Оптимальный маршрут", value=False,
                                help="Добавляет ~5с. Требует горячие точки")
    enable_temporal = st.checkbox("Темпоральная аномалия", value=False)
    enable_drift = st.checkbox("Коррекция дрейфа хотспотов", value=False,
                               help="Добавляет ~10с на скачивание течений")

    st.markdown("**Ветер (наблюдаемый):**")
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        wind_u = st.number_input("U (м/с)", -20.0, 20.0, 0.0, 0.5)
    with col_w2:
        wind_v = st.number_input("V (м/с)", -20.0, 20.0, 0.0, 0.5)

    st.markdown("---")
    # Sentinel-2 rarely covers open ocean; warn users to pick coastal areas
    _is_open_ocean = abs(lat) < 60 and (lon < -30 or lon > 100) and abs(lat) > 10
    _near_land = any([
        13.0 - 2 < lon < 13.0 + 2 and 37.0 - 2 < lat < 37.0 + 2,
        25.0 - 2 < lon < 25.0 + 2 and 37.5 - 2 < lat < 37.5 + 2,
        35.0 - 3 < lon < 35.0 + 3 and 42.5 - 3 < lat < 42.5 + 3,
        -15.0 - 2 < lon < -15.0 + 2 and 28.0 - 2 < lat < 28.0 + 2,
    ])
    if _is_open_ocean and not _near_land:
        st.warning(
            "⚠️ Открытый океан — Sentinel-2 снимает в основном сушу. "
            "Снимки редкие (раз в ~6 месяцев). "
            "Попробуйте Средиземное/Чёрное/Балтийское море."
        )

    run_btn = st.button("🔍 Анализировать", type="primary")


col_logo, col_title = st.columns([1, 8])
with col_title:
    st.markdown("# 🌊 antihype · Карта пластика")
    st.caption(
        "Детекция скоплений морского пластика · Sentinel-2 FDI · "
        "Microsoft Planetary Computer · Экспедиция Фёдора Конюхова"
    )

st.markdown("---")

if run_btn:
    import threading
    import time as _time
    from core.processor import run_pipeline
    from core.currents import get_ocean_currents
    from core.drift import simulate_drift
    from core.route import plan_route
    from core.indices import find_hotspots

    with st.status("Запуск анализа...", expanded=True) as status_box:
        progress_bar = st.progress(0)
        status_line = st.empty()
        timer_line  = st.empty()

        _state = {"msg": "Инициализация...", "pct": 0, "done": False, "result": None, "error": None}

        def progress_cb(msg: str, pct: int):
            _state["msg"] = msg
            _state["pct"] = pct

        def _worker():
            try:
                _state["result"] = run_pipeline(
                    lat=lat, lon=lon,
                    days_back=days_back,
                    buffer=buffer,
                    max_cloud_cover=max_cloud,
                    resolution=resolution,
                    max_scenes=max_scenes,
                    progress_cb=progress_cb,
                    enable_temporal=enable_temporal,
                    enable_drift=enable_drift,
                )
            except Exception as e:
                _state["error"] = str(e)
            finally:
                _state["done"] = True

        t = threading.Thread(target=_worker, daemon=True)
        t_start = _time.time()
        t.start()

        step_icons = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        spin_i = 0
        while not _state["done"]:
            elapsed = _time.time() - t_start
            m, s = int(elapsed // 60), int(elapsed % 60)
            spin = step_icons[spin_i % len(step_icons)]
            pct = _state["pct"]
            msg = _state["msg"]

            progress_bar.progress(pct)
            status_line.markdown(f"**{spin} {msg}**")
            timer_line.markdown(
                f"⏱️ `{m:02d}:{s:02d}` прошло &nbsp;|&nbsp; "
                f"{'█' * (pct // 10)}{'░' * (10 - pct // 10)} `{pct}%`"
            )
            spin_i += 1
            _time.sleep(0.4)

        elapsed_total = _time.time() - t_start
        timer_line.empty()
        status_line.empty()

        if _state["error"]:
            st.error(f"❌ Ошибка: {_state['error']}")
            st.stop()

        result = _state["result"]
        st.session_state.result = result
        progress_bar.progress(100)
        st.write(f"✅ Пайплайн завершён за **{elapsed_total:.1f}с**")

        if result.success:
            st.write("📍 Поиск горячих точек...")
            hotspots = find_hotspots(result.fdi, result.plastic_mask, result.lats, result.lons)
            st.session_state.hotspots = hotspots

            if include_drift or include_route:
                st.write("🌊 Загрузка данных о течениях...")
                currents = get_ocean_currents(lat, lon, buffer=2.0)
                if not currents.get("is_synthetic"):
                    st.write(f"✅ Течения: {currents.get('source', 'реальные данные')}")
                st.session_state.currents = currents

            if include_drift and hotspots:
                st.write("🔮 Расчёт прогноза дрейфа...")
                top = hotspots[0]
                drift = simulate_drift(top["lat"], top["lon"], currents, hours=72)
                st.session_state.drift_result = drift

            if include_route and hotspots:
                st.write("🧭 Оптимизация маршрута (с учётом дрейфа)...")
                route = plan_route(lat, lon, hotspots,
                                   currents=st.session_state.get("currents"))
                st.session_state.route_result = route

        status_box.update(
            label="✅ Анализ завершён!" if result.success else "⚠️ Снимки не найдены",
            state="complete" if result.success else "error",
        )

result = st.session_state.result

if result is None:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        **🛰️ Данные**
        - Sentinel-2 L2A
        - 100м разрешение (настраиваемо)
        - Microsoft Planetary Computer
        - Обновление каждые 5 дней
        """)
    with c2:
        st.markdown("""
        **🔬 Алгоритм**
        - FDI (Biermann 2020)
        - FAI, PI, NDVI индексы
        - SCL маска облаков
        - Медианный композит
        """)
    with c3:
        st.markdown("""
        **⚡ Возможности**
        - Прогноз дрейфа 72ч
        - Оптимальный маршрут
        - PDF отчёт
        - REST API
        """)

    with st.expander("📖 Формула FDI — Floating Debris Index"):
        st.latex(r"FDI = B_{8A} - \left[B_6 + (B_{11} - B_6) \cdot \frac{\lambda_{8A} - \lambda_6}{\lambda_{11} - \lambda_6}\right]")
        st.markdown("""
        | Канал | λ, нм | Роль |
        |-------|-------|------|
        | B6 | 740 | Red Edge 2 — базовая линия |
        | B8A | 865 | NIR — целевой канал |
        | B11 | 1610 | SWIR 1 — базовая линия |

        **Почему работает:** пластик имеет повышенное отражение в NIR относительно чистой воды,
        создавая положительную аномалию FDI. Биологический мусор (Саргассум) фильтруется через NDVI.

        > Biermann et al. (2020) *Scientific Reports* 10:5364
        """)
    st.stop()

if not result.success:
    st.error("⚠️ Снимки Sentinel-2 не найдены за указанный период.")
    for w in result.warnings:
        st.warning(w)
    st.info("Советы: увеличьте период (дней), повысьте % облачности, измените координаты.")
    st.stop()

for w in result.warnings:
    st.warning(f"⚠️ {w}")

s = result.stats
c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
c1.metric("🔴 Пластик", f"{s.get('plastic_coverage_pct',0):.3f}%")
c2.metric("📐 Площадь", f"{s.get('plastic_area_km2',0):.2f} км²")
c3.metric("📈 FDI макс / Порог", f"{s.get('fdi_max',0):.4f} / {s.get('fdi_threshold_used','?')}")
c4.metric("☁️ Облачность", f"{s.get('cloud_coverage_pct','?')}%")
c5.metric("🛰️ Снимков", result.scenes_found)
c6.metric("⏱️ Время", f"{result.processing_time_sec}с")
c7.metric("🎯 Уверенность", f"{s.get('confidence_mean',0):.1%}")
c8.metric("✨ Glint", f"{s.get('glint_pixels',0)}")

st.caption(f"📅 Снимки: {', '.join(result.scene_dates)} · Центр: {lat:.4f}°N, {lon:.4f}°E")

st.markdown("---")

if result.confidence_map is not None:
    with st.expander("🎯 Карта уверенности детекции"):
        import matplotlib.pyplot as plt
        fig_conf, ax_conf = plt.subplots(1, 1, figsize=(10, 6), facecolor="#07111f")
        ax_conf.set_facecolor("#07111f")
        im_conf = ax_conf.imshow(result.confidence_map, cmap="RdYlGn_r",
                                  extent=[result.lons.min(), result.lons.max(),
                                          result.lats.min(), result.lats.max()],
                                  origin="upper", aspect="auto", vmin=0, vmax=1)
        ax_conf.set_title("Карта уверенности (0=низкая, 1=высокая)", color="white", fontsize=12)
        ax_conf.tick_params(colors="#888")
        for sp in ax_conf.spines.values():
            sp.set_edgecolor("#333")
        cbar = fig_conf.colorbar(im_conf, ax=ax_conf, fraction=0.046)
        cbar.set_label("Уверенность", color="white")
        cbar.ax.yaxis.set_tick_params(color="white")
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
        plt.tight_layout()
        st.pyplot(fig_conf)
        plt.close(fig_conf)

tab_map, tab_indices, tab_drift, tab_route, tab_report, tab_export = st.tabs([
    "🗺️ Карта",
    "📊 Индексы",
    "🌊 Дрейф",
    "🧭 Маршрут",
    "📄 Отчёт",
    "💾 Экспорт",
])

with tab_map:
    from viz.maps import make_folium_map

    hotspots = st.session_state.hotspots or []
    drift_result = st.session_state.drift_result

    m = make_folium_map(
        lat=lat, lon=lon,
        fdi=result.fdi,
        plastic_mask=result.plastic_mask,
        lons=result.lons,
        lats=result.lats,
        cloud_mask=result.cloud_mask,
        stats=result.stats,
        scene_dates=result.scene_dates,
        hotspots=hotspots,
        drift_result=drift_result,
        route_result=st.session_state.route_result,
        confidence_map=result.confidence_map,
        hotspots_drift_corrected=result.hotspots_drift_corrected,
    )

    map_html = m._repr_html_()
    html_bytes = m.get_root().render().encode("utf-8")
    st.session_state["map_html_bytes"] = html_bytes
    components.html(map_html, height=580, scrolling=False)

    if hotspots:
        st.markdown(f"**📍 Горячих точек обнаружено: {len(hotspots)}**")
        hs_df = {
            "#": list(range(1, min(len(hotspots), 8) + 1)),
            "Широта": [f"{h['lat']:.4f}°" for h in hotspots[:8]],
            "Долгота": [f"{h['lon']:.4f}°" for h in hotspots[:8]],
            "FDI макс": [f"{h['fdi_max']:.5f}" for h in hotspots[:8]],
            "Площадь км²": [f"{h['area_km2']:.3f}" for h in hotspots[:8]],
        }
        st.table(hs_df)

    if result.hotspots_drift_corrected and result.hotspots_drift_corrected != hotspots:
        st.markdown("**🔄 Скорректированные по дрейфу:**")
        dc_df = {
            "#": list(range(1, min(len(result.hotspots_drift_corrected), 8) + 1)),
            "Широта": [f"{h['lat']:.4f}°" for h in result.hotspots_drift_corrected[:8]],
            "Долгота": [f"{h['lon']:.4f}°" for h in result.hotspots_drift_corrected[:8]],
            "Дрейф км": [f"{h.get('drift_km', 0):.1f}" for h in result.hotspots_drift_corrected[:8]],
            "Дрейф ч": [f"{h.get('drift_hours', 0):.0f}" for h in result.hotspots_drift_corrected[:8]],
        }
        st.table(dc_df)


with tab_indices:
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    st.markdown("### Сравнение спектральных индексов")
    st.markdown(
        "Каждый индекс по-своему чувствителен к плавающему мусору. "
        "Сравнение помогает отличить пластик от водорослей (Саргассум) и пены."
    )

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.markdown("""
        | Индекс | Чувствителен к | Фильтрует |
        |--------|---------------|-----------|
        | **FDI** | Пластик, пена | Чистая вода |
        | **FAI** | Водоросли + пластик | — |
        | **PI** | Пластик (NIR/Red) | Вода, земля |
        | **NDVI** | Водоросли | Пластик, вода |
        """)
    with col_info2:
        st.markdown("""
        **Логика детекции пластика:**
        1. FDI > порог → плавающий материал
        2. NDWI > 0 → водный пиксель
        3. NDVI < 0.15 → не водоросли

        Только пиксели, прошедшие **все 3 условия** = пластик (красный).
        """)

    fig, axes = plt.subplots(2, 3, figsize=(16, 9), facecolor="#07111f")
    fig.suptitle("Анализ спектральных индексов", color="white", fontsize=14, fontweight="bold")

    fdi_arr = result.fdi

    def _plot_index(ax, data, title, cmap, vmin=None, vmax=None, label=""):
        ax.set_facecolor("#07111f")
        if vmin is None:
            vmin = np.nanpercentile(data, 2)
        if vmax is None:
            vmax = np.nanpercentile(data, 98)
        im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax,
                       extent=[result.lons.min(), result.lons.max(),
                               result.lats.min(), result.lats.max()],
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
                      extent=[result.lons.min(), result.lons.max(),
                              result.lats.min(), result.lats.max()],
                      origin="upper", aspect="auto", vmin=0, vmax=1)
    axes[0, 1].set_title("Бинарная маска\n(синий=вода, красный=пластик)", color="white", fontsize=10, pad=4)
    axes[0, 1].tick_params(colors="#888", labelsize=7)
    for sp in axes[0, 1].spines.values():
        sp.set_edgecolor("#333")

    if result.cloud_mask is not None:
        _plot_index(axes[0, 2], result.cloud_mask,
                    "Маска облачности (SCL)\n(0=ясно, 1=облака)",
                    "Greys", 0, 1, "Облачность")
    else:
        axes[0, 2].set_visible(False)

    axes[1, 0].set_facecolor("#112240")
    valid_fdi = fdi_arr[~np.isnan(fdi_arr)]
    if valid_fdi.size > 0:
        axes[1, 0].hist(valid_fdi, bins=80, range=(-0.05, 0.1),
                        color="#4fc3f7", alpha=0.8, edgecolor="none")
        fdi_thresh = result.stats.get("fdi_threshold_used", 0.005)
        axes[1, 0].axvline(fdi_thresh, color="#ff5252", linestyle="--", linewidth=1.5,
                           label=f"Порог FDI={fdi_thresh:.4f}")
        axes[1, 0].axvline(0, color="#aaa", linestyle=":", linewidth=1, alpha=0.7)
        axes[1, 0].set_title("Распределение FDI", color="white", fontsize=10)
        axes[1, 0].set_xlabel("FDI", color="#888", fontsize=8)
        axes[1, 0].set_ylabel("Пикселей", color="#888", fontsize=8)
        axes[1, 0].tick_params(colors="#888", labelsize=7)
        axes[1, 0].legend(fontsize=8, labelcolor="white",
                          facecolor="#1a2a3a", edgecolor="#333")
        for sp in axes[1, 0].spines.values():
            sp.set_edgecolor("#333")

    axes[1, 1].set_facecolor("#112240")
    plastic_pct = s.get("plastic_coverage_pct", 0)
    cloud_pct_val = s.get("cloud_coverage_pct", 0) or 0
    water_pct = max(0, 100 - plastic_pct - float(cloud_pct_val))
    sizes = [plastic_pct, float(cloud_pct_val), water_pct]
    labels = [f"Пластик\n{plastic_pct:.3f}%", f"Облака\n{cloud_pct_val:.1f}%",
              f"Чистая вода\n{water_pct:.1f}%"]
    explode = (0.05, 0, 0)
    wedges, texts, autotexts = axes[1, 1].pie(
        sizes, labels=labels, autopct="%1.1f%%",
        colors=["#ff5252", "#90a4ae", "#1565c0"],
        explode=explode, startangle=90,
        textprops={"color": "white", "fontsize": 7},
        pctdistance=0.75,
    )
    axes[1, 1].set_title("Состав пикселей", color="white", fontsize=10)

    axes[1, 2].set_facecolor("#112240")
    metrics = ["FDI макс", "FDI среднее", "FDI P95"]
    vals = [
        s.get("fdi_max") or 0,
        s.get("fdi_mean") or 0,
        s.get("fdi_p95") or 0,
    ]
    bars = axes[1, 2].bar(metrics, vals,
                           color=["#ff5252", "#4fc3f7", "#ffb74d"],
                           alpha=0.85, edgecolor="none")
    axes[1, 2].axhline(0.005, color="#ff5252", linestyle="--", linewidth=1,
                        label="Порог", alpha=0.7)
    axes[1, 2].set_title("Ключевые метрики FDI", color="white", fontsize=10)
    axes[1, 2].tick_params(colors="#888", labelsize=8)
    for sp in axes[1, 2].spines.values():
        sp.set_edgecolor("#333")
    axes[1, 2].yaxis.set_tick_params(color="#888")
    for bar, val in zip(bars, vals):
        axes[1, 2].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0003,
                         f"{val:.4f}", ha="center", va="bottom",
                         color="white", fontsize=8)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


with tab_drift:
    st.markdown("### 🌊 Прогноз дрейфа пластика")

    drift_result = st.session_state.drift_result
    currents = st.session_state.currents

    if drift_result is None:
        if result is not None and result.success and not st.session_state.hotspots:
            st.info("Горячих точек не обнаружено — дрейф рассчитывать не для чего.")
        elif result is not None and result.success:
            st.info("Включите «Прогноз дрейфа» в боковой панели и нажмите «Анализировать».")
        else:
            st.info("Сначала запустите анализ.")
    else:
        dr = drift_result

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("📍 Смещение 24ч", f"{dr.distance_km_24h:.1f} км")
        col2.metric("📍 Смещение 48ч", f"{dr.distance_km_48h:.1f} км")
        col3.metric("🌊 Течение", f"{dr.current_speed_ms:.2f} м/с",
                    f"{dr.current_direction_deg:.0f}°")
        col4.metric("💨 Ветер", f"{getattr(dr,'wind_speed_ms',0):.1f} м/с",
                    f"{getattr(dr,'wind_direction_deg',0):.0f}°")
        col5.metric("🎯 Неопред. 24ч", f"±{getattr(dr,'uncertainty_km_24h',0):.1f} км")
        col6.metric("🎯 Неопред. 48ч", f"±{getattr(dr,'uncertainty_km_48h',0):.1f} км")

        _src = st.session_state.currents.get("source", "") if st.session_state.currents else ""
        if dr.is_synthetic:
            st.caption("ℹ️ Синтетическая модель (Open-Meteo недоступен).")
        else:
            st.caption(f"📡 Источник: **{_src}** · Ансамбль: 30 частиц · Физика: течение + стоксов дрейф + парусность пластика 2.5%")

        import folium
        from folium import plugins

        dm = folium.Map(location=[lat, lon], zoom_start=6, tiles=None)
        folium.TileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri", name="Спутник", overlay=False, control=True,
        ).add_to(dm)
        folium.TileLayer("CartoDB dark_matter", name="Тёмная", overlay=False, control=True).add_to(dm)

        traj_coords = [(p[0], p[1]) for p in dr.trajectory[::2]]
        folium.PolyLine(
            traj_coords, color="#ff7043", weight=2.5, opacity=0.8,
            tooltip="Траектория дрейфа",
        ).add_to(dm)

        folium.CircleMarker(
            [dr.origin_lat, dr.origin_lon], radius=8,
            color="#ff5252", fill=True, fill_opacity=0.9,
            tooltip=f"Начало: {dr.origin_lat:.4f}°N, {dr.origin_lon:.4f}°E",
        ).add_to(dm)

        if dr.positions_24h:
            folium.Marker(
                [dr.positions_24h[0], dr.positions_24h[1]],
                tooltip=f"Через 24ч: {dr.positions_24h[0]:.4f}°N, {dr.positions_24h[1]:.4f}°E\n"
                        f"Смещение: {dr.distance_km_24h:.1f} км",
                icon=folium.DivIcon(html="""
                    <div style="background:#ff9800;color:white;padding:3px 6px;
                                border-radius:4px;font-size:11px;font-weight:bold;
                                white-space:nowrap;box-shadow:1px 1px 3px rgba(0,0,0,0.5)">
                    ⏰ 24ч</div>"""),
            ).add_to(dm)

        if dr.positions_48h:
            folium.Marker(
                [dr.positions_48h[0], dr.positions_48h[1]],
                tooltip=f"Через 48ч: {dr.positions_48h[0]:.4f}°N, {dr.positions_48h[1]:.4f}°E\n"
                        f"Смещение: {dr.distance_km_48h:.1f} км",
                icon=folium.DivIcon(html="""
                    <div style="background:#f44336;color:white;padding:3px 6px;
                                border-radius:4px;font-size:11px;font-weight:bold;
                                white-space:nowrap;box-shadow:1px 1px 3px rgba(0,0,0,0.5)">
                    ⏰ 48ч</div>"""),
            ).add_to(dm)

        if dr.positions_72h:
            folium.Marker(
                [dr.positions_72h[0], dr.positions_72h[1]],
                tooltip=f"Через 72ч: {dr.positions_72h[0]:.4f}°N, {dr.positions_72h[1]:.4f}°E",
                icon=folium.DivIcon(html="""
                    <div style="background:#9c27b0;color:white;padding:3px 6px;
                                border-radius:4px;font-size:11px;font-weight:bold;
                                white-space:nowrap;box-shadow:1px 1px 3px rgba(0,0,0,0.5)">
                    ⏰ 72ч</div>"""),
            ).add_to(dm)

        if currents is not None:
            curr_lats = currents["lats"]
            curr_lons = currents["lons"]
            u_grid = currents["u"]
            v_grid = currents["v"]

            step_y = max(1, len(curr_lats) // 10)
            step_x = max(1, len(curr_lons) // 10)
            for i in range(0, len(curr_lats), step_y):
                for j in range(0, len(curr_lons), step_x):
                    u_val = u_grid[i, j] if not np.isnan(u_grid[i, j]) else 0
                    v_val = v_grid[i, j] if not np.isnan(v_grid[i, j]) else 0
                    speed = np.sqrt(u_val**2 + v_val**2)
                    if speed < 0.01:
                        continue
                    angle = float(np.degrees(np.arctan2(u_val, v_val))) % 360
                    clat, clon = float(curr_lats[i]), float(curr_lons[j])
                    folium.RegularPolygonMarker(
                        location=[clat, clon],
                        number_of_sides=3,
                        rotation=angle,
                        radius=5,
                        color="#29b6f6",
                        fill=True,
                        fill_opacity=0.6,
                        tooltip=f"U={u_val:.2f} м/с, V={v_val:.2f} м/с",
                    ).add_to(dm)

        folium.LayerControl().add_to(dm)
        plugins.Fullscreen().add_to(dm)
        components.html(dm._repr_html_(), height=500, scrolling=False)

        st.markdown("**📋 Прогнозные позиции:**")
        positions = []
        for label, pos, dist in [
            ("24ч", dr.positions_24h, dr.distance_km_24h),
            ("48ч", dr.positions_48h, dr.distance_km_48h),
            ("72ч", dr.positions_72h, None),
        ]:
            if pos:
                positions.append({
                    "Горизонт": label,
                    "Широта": f"{pos[0]:.4f}°N",
                    "Долгота": f"{pos[1]:.4f}°E",
                    "Смещение, км": f"{dist:.1f}" if dist else "—",
                })
        st.table(positions)


with tab_route:
    st.markdown("### 🧭 Оптимальный маршрут плота")

    route_result = st.session_state.route_result
    hotspots = st.session_state.hotspots or []

    if not hotspots:
        st.info("Горячих точек не обнаружено — маршрут строить не к чему.")
    elif route_result is None:
        st.info("Включите «Оптимальный маршрут» в боковой панели и нажмите «Анализировать».")
    else:
        rr = route_result

        if rr.waypoints:
            wp1 = rr.waypoints[0]
            st.markdown(f"""
            <div style="background:#112240;border:2px solid #1565c0;border-radius:12px;padding:20px;text-align:center;margin:10px 0">
                <div style="color:#90caf9;font-size:14px">СЛЕДУЮЩАЯ ТОЧКА</div>
                <div style="color:#4fc3f7;font-size:36px;font-weight:bold">{wp1.bearing_from_prev_deg:.0f}&deg;</div>
                <div style="color:white;font-size:18px">{wp1.distance_from_prev_km:.1f} км &middot; ETA {wp1.eta_hours:.1f}ч</div>
                <div style="color:#90caf9;font-size:12px">{wp1.lat:.4f}&deg;N, {wp1.lon:.4f}&deg;E &middot; {wp1.label}</div>
            </div>
            """, unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📍 Точек маршрута", rr.n_hotspots)
        col2.metric("📏 Расстояние", f"{rr.total_distance_km:.1f} км")
        col3.metric("⏱️ ETA", f"{rr.total_eta_hours:.1f} ч")
        col4.metric("📅 Дней в пути", f"{rr.total_eta_days:.1f}")

        st.caption(f"Скорость плота: ~2 узла (~3.7 км/ч). Метод: Greedy + 2-opt оптимизация.")

        import folium
        rm = folium.Map(location=[lat, lon], zoom_start=7, tiles=None)
        folium.TileLayer(
            "CartoDB dark_matter", name="Тёмная", overlay=False, control=True,
        ).add_to(rm)
        folium.TileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri", name="Спутник", overlay=False, control=True,
        ).add_to(rm)

        route_coords = [(lat, lon)] + [(wp.lat, wp.lon) for wp in rr.waypoints]
        folium.PolyLine(
            route_coords, color="#00e5ff", weight=3, opacity=0.9,
            dash_array="8 4", tooltip="Маршрут плота",
        ).add_to(rm)

        folium.Marker(
            [lat, lon],
            tooltip="🚢 Текущая позиция плота",
            icon=folium.Icon(color="blue", icon="ship", prefix="fa"),
        ).add_to(rm)

        for i, wp in enumerate(rr.waypoints):
            color_hex = "#ff5252" if wp.fdi_max > 0.01 else "#ff9800"
            folium.CircleMarker(
                [wp.lat, wp.lon],
                radius=8 + int(wp.area_km2 * 2),
                color=color_hex,
                fill=True,
                fill_opacity=0.8,
                tooltip=(
                    f"{wp.label} | ETA: {wp.eta_hours:.1f}ч\n"
                    f"Курс: {wp.bearing_from_prev_deg:.0f}° | "
                    f"Dist: {wp.distance_from_prev_km:.1f}км\n"
                    f"FDI: {wp.fdi_max:.4f} | {wp.area_km2:.3f} км²"
                ),
            ).add_to(rm)
            folium.DivIcon(html=f"""
                <div style="background:{color_hex};color:white;padding:2px 5px;
                            border-radius:3px;font-size:10px;font-weight:bold">
                {wp.label}</div>"""
            )

        folium.LayerControl().add_to(rm)
        components.html(rm._repr_html_(), height=480, scrolling=False)

        st.markdown("**📋 Навигационная таблица:**")
        wp_data = {
            "WP": [wp.label for wp in rr.waypoints],
            "Широта": [f"{wp.lat:.4f}°" for wp in rr.waypoints],
            "Долгота": [f"{wp.lon:.4f}°" for wp in rr.waypoints],
            "Курс": [f"{wp.bearing_from_prev_deg:.0f}°" for wp in rr.waypoints],
            "Расст., км": [f"{wp.distance_from_prev_km:.1f}" for wp in rr.waypoints],
            "ETA, ч": [f"{wp.eta_hours:.1f}" for wp in rr.waypoints],
            "FDI макс": [f"{wp.fdi_max:.4f}" for wp in rr.waypoints],
            "Площадь км²": [f"{wp.area_km2:.3f}" for wp in rr.waypoints],
        }
        st.table(wp_data)


with tab_report:
    st.markdown("### 📄 Миссионный отчёт")
    st.markdown(
        "Автоматически генерируется PDF с картами, статистикой, "
        "прогнозом дрейфа и маршрутом."
    )

    col_gen, col_info = st.columns([1, 2])
    with col_gen:
        if st.button("📄 Сгенерировать PDF"):
            with st.spinner("Генерация отчёта..."):
                try:
                    from core.report import generate_pdf_report
                    pdf_bytes = generate_pdf_report(
                        lat=lat, lon=lon,
                        stats=result.stats,
                        fdi=result.fdi,
                        plastic_mask=result.plastic_mask,
                        lons_arr=result.lons,
                        lats_arr=result.lats,
                        cloud_mask=result.cloud_mask,
                        scene_dates=result.scene_dates,
                        hotspots=st.session_state.hotspots,
                        drift_result=st.session_state.drift_result,
                        route_result=st.session_state.route_result,
                    )
                    st.session_state["pdf_bytes"] = pdf_bytes
                    st.success("✅ Отчёт готов!")
                except ImportError:
                    st.error("Установите reportlab: `pip install reportlab`")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

    if "pdf_bytes" in st.session_state and st.session_state["pdf_bytes"]:
        st.download_button(
            label="⬇️ Скачать PDF",
            data=st.session_state["pdf_bytes"],
            file_name=f"antihype_report_{lat:.2f}_{lon:.2f}.pdf",
            mime="application/pdf",
        )

    with col_info:
        st.markdown("""
        **Содержание отчёта:**
        - 📋 Параметры миссии
        - 📊 Таблица статистики
        - 🗺️ Карта FDI + детекции пластика
        - 📍 Список горячих точек с координатами
        - 🌊 Прогноз дрейфа (если включён)
        - 🧭 Навигационная таблица маршрута
        - 📚 Методологический раздел (для жюри)
        """)


with tab_export:
    st.markdown("### 💾 Экспорт данных")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**🗺️ Карта**")
        if "map_html_bytes" in st.session_state:
            html_bytes = st.session_state["map_html_bytes"]
        else:
            from viz.maps import make_folium_map
            m_export = make_folium_map(
                lat=lat, lon=lon,
                fdi=result.fdi, plastic_mask=result.plastic_mask,
                lons=result.lons, lats=result.lats,
                cloud_mask=result.cloud_mask, stats=result.stats,
                scene_dates=result.scene_dates,
            )
            html_bytes = m_export.get_root().render().encode("utf-8")
        st.download_button(
            "🗺️ HTML (интерактивная)",
            data=html_bytes,
            file_name=f"plastic_map_{lat:.2f}_{lon:.2f}.html",
            mime="text/html",
        )

        from viz.plots import make_static_png
        png_bytes = make_static_png(
            fdi=result.fdi, plastic_mask=result.plastic_mask,
            lons=result.lons, lats=result.lats,
            lat=lat, lon=lon, cloud_mask=result.cloud_mask,
            stats=result.stats, scene_dates=result.scene_dates,
        )
        st.download_button(
            "🖼️ PNG (статичная)",
            data=png_bytes,
            file_name=f"plastic_map_{lat:.2f}_{lon:.2f}.png",
            mime="image/png",
        )

    with col2:
        st.markdown("**📊 Данные**")

        hotspots = st.session_state.hotspots or []
        if hotspots:
            geojson = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [h["lon"], h["lat"]]},
                        "properties": h,
                    }
                    for h in hotspots
                ],
            }
            st.download_button(
                "📍 GeoJSON (горячие точки)",
                data=json.dumps(geojson, ensure_ascii=False, indent=2),
                file_name=f"hotspots_{lat:.2f}_{lon:.2f}.geojson",
                mime="application/geo+json",
            )

        if st.session_state.route_result:
            from core.route import route_to_geojson
            route_geojson = route_to_geojson(st.session_state.route_result)
            st.download_button(
                "🧭 GeoJSON (маршрут)",
                data=json.dumps(route_geojson, ensure_ascii=False, indent=2),
                file_name=f"route_{lat:.2f}_{lon:.2f}.geojson",
                mime="application/geo+json",
            )

        st.download_button(
            "📈 JSON (статистика)",
            data=json.dumps({
                "lat": lat, "lon": lon,
                "scene_dates": result.scene_dates,
                "stats": result.stats,
                "hotspots": hotspots,
                "warnings": result.warnings,
            }, ensure_ascii=False, indent=2),
            file_name=f"stats_{lat:.2f}_{lon:.2f}.json",
            mime="application/json",
        )

    with col3:
        st.markdown("**🔢 Растровые данные**")

        if result.fdi is not None:
            import pandas as pd
            step = max(1, result.fdi.shape[0] // 200)
            fdi_sub = result.fdi[::step, ::step]
            lats_sub = result.lats[::step]
            lons_sub = result.lons[::step]
            plastic_sub = result.plastic_mask[::step, ::step]
            lons_mg, lats_mg = np.meshgrid(lons_sub, lats_sub)
            fdi_flat = fdi_sub.flatten()
            plastic_flat = plastic_sub.flatten().astype(int)
            valid = ~np.isnan(fdi_flat)

            df = pd.DataFrame({
                "lat": lats_mg.flatten()[valid],
                "lon": lons_mg.flatten()[valid],
                "fdi": fdi_flat[valid],
                "plastic": plastic_flat[valid],
            })
            if len(df) > 50000:
                df = df.sample(50000, random_state=42).sort_values(["lat", "lon"])

            st.download_button(
                "📉 CSV (FDI пиксели, 50k сэмпл)",
                data=df.to_csv(index=False),
                file_name=f"fdi_pixels_{lat:.2f}_{lon:.2f}.csv",
                mime="text/csv",
            )
