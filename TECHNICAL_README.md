# EcoHack: Алгоритм-разведчик — карта пластика для капитана

## Оглавление
- [Суть проекта](#суть-проекта)
- [Что перекинуть на ПК](#что-перекинуть-на-пк)
- [Структура проекта](#структура-проекта)
- [Архитектура системы](#архитектура-системы)
- [Core: алгоритмическое ядро](#core-алгоритмическое-ядро)
- [Apps: интерфейсы](#apps-интерфейсы)
- [Viz: визуализация](#viz-визуализация)
- [Сборка и дистрибуция](#сборка-и-дистрибуция)
- [Конфигурация и пороги](#конфигурация-и-пороги)
- [Зависимости](#зависимости)
- [Тестирование](#тестирование)
- [Известные ограничения](#известные-ограничения)
- [Что можно улучшить далее](#что-можно-улучшить-далее)

---

## Суть проекта

**Кейс 7 EcoHack**: прототип для экспедиции Фёдора Конюхова. Капитан на плоту с ограниченным спутниковым интернетом и обычным ноутбуком вводит координаты → система автоматически скачивает спутниковые снимки Sentinel-2 → рассчитывает индекс плавающего мусора (FDI) → показывает карту с горячими точками, прогнозом дрейфа и оптимальным маршрутом.

**ТЗ** (дословно): файл `ТЗ ecohack.txt` в корне проекта.

**Критерии оценки**:
- 30% — автоматизация (от загрузки до визуализации без ручных действий)
- 30% — удобство интерфейса для не-специалиста (капитана)
- 20% — корректность спектрального индекса и обоснование
- 10% — решение для облачности
- 10% — качество презентации

---

## Что перекинуть на ПК

### Вариант 1: Полная копия (разработка)
Скопировать целиком `/root/ecohack/`. Это ~1.1 ГБ из-за `dist_standalone/python_env/`.

### Вариант 2: Только код (без встроенного Python)
```
ecohack/
├── core/              ← алгоритмы (обязательно)
├── apps/              ← интерфейсы (обязательно)
├── viz/               ← визуализация (обязательно)
├── config.py          ← конфигурация (обязательно)
├── requirements.txt   ← зависимости (обязательно)
├── build_exe.py       ← сборка .exe
├── ecohack.spec       ← PyInstaller spec Lite
├── ecohack_full.spec  ← PyInstaller spec Full
├── launchers/         ← ярлыки запуска (с системным Python)
└── ТЗ ecohack.txt     ← техническое задание
```
Потом: `pip install -r requirements.txt` и запускать через `launchers/`.

### Вариант 3: Для конечного пользователя (капитана)
Скопировать только `dist_standalone/`. Содержит:
- Встроенный Python + все зависимости
- Код проекта
- Ярлыки `.bat` / `.sh` для запуска одним кликом
- `setup_windows.bat` / `setup.sh` — первичная установка

Пользователь запускает `setup_windows.bat` (один раз), потом кликает `EcoHack_Lite.bat`.

---

## Структура проекта

```
ecohack/                          ← корень проекта
│
├── config.py                     ← глобальная конфигурация: пороги, каналы, URL
│
├── core/                         ← алгоритмическое ядро (2,975 строк)
│   ├── __init__.py               ← экспорт run_pipeline
│   ├── processor.py        424   ← ГЛАВНЫЙ ФАЙЛ: оркестратор пайплайна
│   ├── data_loader.py      221   ← загрузка Sentinel-2 через STAC + stackstac
│   ├── data_loader_s3.py   284   ← альтернативные источники (S3, MODIS, CDSE)
│   ├── cloud_mask.py        93   ← SCL маскировка облаков + медианный композит
│   ├── indices.py          633   ← FDI, FAI, PI, NDVI, NDWI + маска пластика
│   ├── currents.py         278   ← океанские течения (Open-Meteo / HYCOM / синтетика)
│   ├── drift.py            286   ← ансамблевый дрейф (RK4, 30 частиц, 72ч)
│   ├── route.py            349   ← маршрутизация (greedy + 2-opt + дрейф-коррекция)
│   ├── timeseries.py       202   ← временные ряды FDI по rolling-окнам
│   └── report.py           402   ← генерация PDF-отчёта (ReportLab)
│
├── viz/                          ← визуализация (689 строк)
│   ├── __init__.py               ← экспорт make_folium_map, make_static_png
│   ├── maps.py             421   ← интерактивная Folium карта (FDI overlay,
│   │                               confidence overlay, дрейф, маршрут, хотспоты)
│   └── plots.py            264   ← статический PNG (matplotlib, масштаб. линейка)
│
├── apps/                         ← интерфейсы (2,445 строк)
│   ├── streamlit_app.py   1047   ← полный Streamlit UI (6 вкладок)
│   ├── api.py              320   ← FastAPI REST API + Swagger
│   ├── cli.py              260   ← минимальный CLI (argparse)
│   ├── cli_rich.py         235   ← Rich CLI (таблицы, прогресс-бары)
│   ├── lite_gui.py         326   ← Bottle + Leaflet SPA (для .exe)
│   ├── lite_web.py         197   ← Bottle HTML-only (<50KB, спутниковый инет)
│   └── streamlit_runner.py  60   ← обёртка для PyInstaller-сборки Streamlit
│
├── launchers/                    ← ярлыки запуска (используют системный Python)
│   ├── EcoHack_Lite.bat / .sh / .command
│   ├── EcoHack_Full.bat / .sh / .command
│   ├── EcoHack_LiteWeb.bat / .sh
│   ├── EcoHack_API.bat / .sh
│   └── Install_Dependencies.bat / .sh
│
├── dist_standalone/              ← автономная сборка (Python встроен)
│   ├── python_env/               ← встроенный Python 3.10 + все зависимости
│   ├── ecohack/                  ← копия кода проекта
│   ├── EcoHack_Lite.bat / .sh    ← ярлыки (используют python_env/)
│   ├── EcoHack_Full.bat / .sh
│   ├── EcoHack_LiteWeb.bat / .sh
│   ├── EcoHack_API.bat / .sh
│   ├── setup_windows.bat         ← скачивает Python embedded + pip + зависимости
│   ├── setup.sh                  ← создаёт venv из системного Python
│   └── README.txt
│
├── build_exe.py                  ← сборка .exe через PyInstaller
├── ecohack.spec                  ← PyInstaller spec для Lite
├── ecohack_full.spec             ← PyInstaller spec для Full (Streamlit)
├── requirements.txt              ← все зависимости
├── ТЗ ecohack.txt                ← техническое задание кейса
└── TECHNICAL_README.md           ← этот файл
```

**Общий объём кода**: ~6,500 строк Python.

---

## Архитектура системы

### Поток данных

```
Координаты (lat, lon)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  core/processor.py :: run_pipeline()                        │
│                                                             │
│  1. data_loader.py  → STAC поиск → stackstac загрузка      │
│  2. cloud_mask.py   → SCL маскировка → медианный композит   │
│  3. processor.py    → DN авто-масштабирование               │
│  4. indices.py      → FDI, NDWI, NDVI, PI → plastic_mask   │
│  5. indices.py      → confidence_map (0..1)                 │
│  6. indices.py      → morphological filtering               │
│  7. processor.py    → UTM→WGS84 координаты                  │
│  8. indices.py      → find_hotspots (кластеризация)         │
│  9. currents.py     → течения (Open-Meteo/HYCOM/синтетика)  │
│  10. drift.py       → дрейф-коррекция хотспотов             │
│  11. processor.py   → PipelineResult                        │
│                                                             │
│  Опционально:                                               │
│  · timeseries.py    → temporal anomaly (FDI - baseline)     │
│  · drift.py         → 72ч прогноз (30-частиц ансамбль)      │
│  · route.py         → маршрут (greedy + 2-opt + дрейф)      │
│  · report.py        → PDF отчёт                             │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────┐   ┌────────────┐   ┌────────────┐
│ PipelineResult                                 │
│ .fdi            numpy (H,W)                    │
│ .plastic_mask   numpy bool (H,W)               │
│ .confidence_map numpy float (H,W) 0..1         │
│ .cloud_mask     numpy float (H,W) 0..1         │
│ .glint_mask     numpy bool (H,W)               │
│ .hotspots       list[dict]                     │
│ .hotspots_drift_corrected  list[dict]          │
│ .stats          dict                           │
│ .fdi_threshold_used  float                     │
│ .lons, .lats    numpy 1D                       │
│ .scene_dates    list[str]                      │
│ .fdi_anomaly    numpy (H,W) | None             │
└────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│  Интерфейсы (все используют один и тот    │
│  же PipelineResult)                       │
│                                          │
│  Streamlit   → tabs: карта, индексы,     │
│                дрейф, маршрут, PDF, экспорт│
│  FastAPI     → JSON REST                 │
│  CLI         → текст + файлы             │
│  Lite GUI    → Bottle + Leaflet JSON API │
│  Lite Web    → Bottle + inline PNG       │
└──────────────────────────────────────────┘
```

### PipelineResult (dataclass, core/processor.py)

Центральный объект. Все интерфейсы работают с ним. Ключевые поля:

| Поле | Тип | Описание |
|------|-----|----------|
| `fdi` | `np.ndarray (H,W)` | Floating Debris Index, float, NaN=нет данных |
| `plastic_mask` | `np.ndarray bool (H,W)` | True = пиксель классифицирован как пластик |
| `confidence_map` | `np.ndarray float (H,W)` | 0..1, уверенность детекции |
| `cloud_mask` | `np.ndarray float (H,W)` | 0..1, облачность (медиана по снимкам) |
| `glint_mask` | `np.ndarray bool (H,W)` | True = солнечный блик |
| `hotspots` | `list[dict]` | Кластеры: lat, lon, fdi_max, area_km2, confidence |
| `hotspots_drift_corrected` | `list[dict]` | То же, но с коррекцией по течениям |
| `stats` | `dict` | plastic_coverage_pct, plastic_area_km2, fdi_max, confidence_mean, glint_pixels, ... |
| `fdi_threshold_used` | `float` | Адаптивный порог (max(mean+3σ, otsu, floor)) |
| `lons`, `lats` | `np.ndarray 1D` | WGS84 координаты осей |
| `fdi_anomaly` | `np.ndarray | None` | Разница FDI с 90-дневным фоном (опционально) |
| `scene_dates` | `list[str]` | Даты использованных снимков |
| `success` | `bool` (property) | True если fdi не None и scenes_found > 0 |

---

## Core: алгоритмическое ядро

### processor.py — оркестратор

```python
run_pipeline(
    lat, lon,                    # координаты центра
    days_back=3,                 # период поиска (дни)
    buffer=0.5,                  # радиус поиска (градусы, ~55 км)
    max_cloud_cover=90,          # макс. облачность сцены (%)
    resolution=60,               # разрешение (м): 20, 60, 120
    max_scenes=2,                # макс. снимков для композита
    enable_temporal=False,       # темпоральная аномалия (+ 1-2 мин)
    enable_drift=True,           # дрейф-коррекция хотспотов
    progress_cb=callback,        # callback(msg, percent)
) -> PipelineResult
```

**Кэширование**: in-memory, ключ `(lat_round2, lon_round2, days, resolution, temporal, drift)`, TTL 5 мин.

**Валидация**: lat clamped [-90, 90], lon clamped [-180, 180].

### data_loader.py — источник данных

- Источник: **Microsoft Planetary Computer** (бесплатный, без ключа)
- Коллекция: `sentinel-2-l2a`
- Каналы: B03, B04, B06, B08, B8A, B11, SCL
- Загрузка: `pystac-client` → `stackstac.stack()` → lazy xarray DataArray
- Проекция: UTM (автоматическое определение зоны)
- Retry: 3 попытки с 2с паузой на STAC search
- Bbox: клиппинг к валидным географическим координатам
- Fallback: если за `days_back` нет снимков, ищет за 90 дней

### indices.py — спектральные индексы

| Индекс | Формула | Назначение |
|--------|---------|------------|
| **FDI** | `B8A - (B06 + (B11-B06) × (λ8A-λ6)/(λ11-λ6))` | Плавающий мусор (Biermann 2020) |
| **FAI** | `B08 - (B04 + (B11-B04) × (λ8-λ4)/(λ11-λ4))` | Плавающий материал (водоросли + пластик) |
| **PI** | `B08 / B04` | Plastic Index (Kikaki 2020) |
| **NDVI** | `(B08-B04) / (B08+B04)` | Растительность (фильтр Саргассума) |
| **NDWI** | `(B03-B08) / (B03+B08)` | Вода/суша |

**Маска пластика** (многослойная):
1. FDI > адаптивный порог (max(mean+3σ, Otsu, 0.02))
2. FDI > FDI_ABSOLUTE_FLOOR (0.01)
3. NDWI > 0 (водный пиксель)
4. NDVI < 0.2 (не водоросли)
5. PI > 0.48 (Kikaki 2020)
6. B08 < 0.1 (не суша)
7. B11 < 0.05 (не яркий объект)
8. Не солнечный блик
9. Морфологическая фильтрация: кластер ≥ 5 пикселей

**Confidence map**: линейная шкала от порога до P99 среди детектированных пикселей.

**Hotspots**: scipy.ndimage.label кластеризация → центроид, fdi_max, area_km2 (с коррекцией по широте).

### currents.py — океанские течения

Трёхуровневый fallback:
1. **Open-Meteo Marine API** (бесплатный, без ключа) — u/v сетка, ветер 10м
2. **HYCOM via ERDDAP** — глобальная модель океана
3. **Синтетическая модель** — гайр с учётом полушария

### drift.py — прогноз дрейфа

- **Метод**: ансамблевый Лагранжев трекинг, 30 частиц
- **Интегратор**: RK4 (Рунге-Кутта 4-го порядка), dt=0.5ч
- **Физика**: течение + Stokes drift proxy (1.3% от течения) + ветровой leeway (2.5% от ветра)
- **Пертурбации**: ±5% на каждую частицу
- **Выход**: медианная траектория + uncertainty cone (1σ) на 24/48/72ч
- `simulate_drift_multi()` — дрейф для нескольких хотспотов

### route.py — маршрутизация

- **Метод**: Greedy nearest-neighbor → 2-opt improvement
- **Дрейф-awareness**: прогнозирует куда сместится хотспот к моменту прибытия плота
- **Скорость плота**: 2 узла (~3.7 км/ч)
- **Выход**: список waypoints с bearing, distance, ETA

### cloud_mask.py — облачность

- SCL-based маскировка (классы 0,1,3,8,9,10,11 → NaN)
- Фильтрация земли (классы 4,5)
- Медианный композит по времени (removes outliers)
- Автоматический выбор наименее облачных сцен

### report.py — PDF отчёт

- ReportLab, поддержка кириллицы (DejaVuSans)
- Содержание: параметры миссии, статистика, карта FDI, хотспоты, дрейф, маршрут, методология

---

## Apps: интерфейсы

### 1. Streamlit (apps/streamlit_app.py) — порт 8501

Полнофункциональный UI. 6 вкладок:
- **Карта** — интерактивная Folium (FDI overlay, confidence overlay, дрейф, маршрут)
- **Индексы** — matplotlib: FDI, маска, облачность, гистограмма, pie chart, метрики
- **Дрейф** — отдельная Folium карта с траекторией + вектора течений
- **Маршрут** — "СЛЕДУЮЩАЯ ТОЧКА" карточка (курс/км/ETA) + карта + навиг. таблица
- **Отчёт** — генерация и скачивание PDF
- **Экспорт** — HTML карта, PNG, GeoJSON, CSV, JSON

Sidebar: координаты, пресеты, период, облачность, разрешение, ветер U/V, чекбоксы дрейфа/темпоральной/маршрута.

### 2. FastAPI (apps/api.py) — порт 8000

```
GET  /           → HTML info
GET  /health     → {"status": "ok"}
GET  /presets    → список пресетов
POST /analyze    → полный анализ (sync или async)
GET  /analyze/{id} → результат async задачи
POST /drift      → только дрейф
POST /route      → только маршрут
GET  /docs       → Swagger UI
```

TTL-очистка job store (1 час). Дрейф для top-3 хотспотов.

### 3. CLI (apps/cli.py)

```bash
python apps/cli.py --preset med --days 3
python apps/cli.py --lat 37 --lon 13 --temporal --no-drift
python apps/cli.py --preset pacific --json    # машиночитаемый JSON
```

Флаги: `--preset`, `--lat/--lon`, `--days`, `--buffer`, `--cloud`, `--output`, `--no-html`, `--no-png`, `--temporal`, `--no-drift`, `--json`, `--verbose`.

### 4. CLI Rich (apps/cli_rich.py)

То же что CLI, но с Rich: ASCII-баннер, цветные таблицы, прогресс-бар. Те же флаги + `--json`.

### 5. Lite GUI (apps/lite_gui.py) — порт 8090

Bottle + Leaflet SPA. Для .exe и обычного запуска.
- GPS кнопка (HTML5 Geolocation)
- Ввод ветра (U/V м/с)
- Пресеты
- Leaflet карта с Esri satellite tiles
- Хотспоты как CircleMarkers + drift-corrected оранжевые
- Fallback предупреждение если Leaflet CDN недоступен

### 6. Lite Web (apps/lite_web.py) — порт 8088

Bottle, чистый HTML. Для спутникового интернета.
- Страница < 50 KB (HTML ~3KB + PNG ~30-40KB)
- Карта = pre-rendered PNG (base64 inline, 72 DPI)
- GPS кнопка
- In-memory кэш (10 мин TTL)
- Тёмная тема, monospace

---

## Viz: визуализация

### maps.py — Folium интерактивная карта

`make_folium_map()` создаёт:
- 3 базовых слоя (Esri Satellite, CartoDB Dark, OSM)
- FDI heatmap overlay (PLASTIC_CMAP: navy→white→orange→red)
- Confidence overlay (green→yellow→red), переключаемый
- Хотспоты (красные CircleMarkers)
- Drift-corrected хотспоты (оранжевые CircleMarkers)
- Дрейф траектория + uncertainty circles на 24/48/72ч
- Маршрут (cyan PolyLine + waypoints)
- Colorbar legend
- Info panel (статистика)
- Layer control, fullscreen, mouse position

### plots.py — Static PNG

`make_static_png()` создаёт matplotlib figure:
- Panel 1 (опц.): True-color RGB
- Panel 2: FDI heatmap с адаптивной нормализацией + hotspot маркеры
- Panel 3: Бинарная маска (вода/пластик/облака)
- Panel 4 (опц.): Confidence map (RdYlGn_r)
- Масштабная линейка (AnchoredSizeBar, км с учётом широты)
- Footer со статистикой + threshold + confidence

---

## Сборка и дистрибуция

### dist_standalone/ — автономная сборка

Содержит встроенный `python_env/` с Python и всеми зависимостями. Пользователь:
1. Запускает `setup_windows.bat` (Windows) или `setup.sh` (Linux/macOS) — один раз
2. Кликает `EcoHack_Lite.bat` / `.sh` — браузер открывается

### launchers/ — ярлыки с системным Python

Для тех у кого Python уже установлен. Сначала `Install_Dependencies`, потом любой ярлык.

### PyInstaller (.exe)

`build_exe.py` — скрипт сборки:
```bash
python build_exe.py --lite    # → dist/EcoHack_Lite.exe (~30MB)
python build_exe.py --full    # → dist/EcoHack_Full.exe (~100MB)
```

Spec-файлы: `ecohack.spec` (Lite), `ecohack_full.spec` (Full + Streamlit collect-all).

**Важно**: .exe сборка работает только на целевой ОС (Windows .exe — с Windows).

---

## Конфигурация и пороги

Все пороги в `config.py`:

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| `FDI_PLASTIC_THRESHOLD` | 0.02 | Biermann 2020: 0.02–0.06 |
| `FDI_ABSOLUTE_FLOOR` | 0.01 | Фильтрация шума около нуля |
| `NDWI_WATER_THRESHOLD` | 0.0 | McFeeters 1996 |
| `NDVI_MAX_THRESHOLD` | 0.2 | Исключение Саргассума |
| `PI_PLASTIC_THRESHOLD` | 0.48 | Kikaki 2020 |
| `NIR_MAX_REFLECTANCE` | 0.1 | Исключение суши |
| `SWIR_MAX_REFLECTANCE` | 0.05 | Исключение ярких объектов |
| `MIN_CLUSTER_PIXELS` | 5 | Минимальный кластер (при 60м = 18,000 м²) |
| `MAX_CLOUD_COVER` | 90 | Scene-level фильтр (%), pixel-level маскируется отдельно |
| `TARGET_RESOLUTION` | 60 | Метры на пиксель (20/60/120) |
| `DEFAULT_BUFFER_DEG` | 0.5 | ~55 км по каждой стороне |
| `FALLBACK_DAYS_BACK` | 90 | Fallback окно поиска |

Источник данных: `PC_STAC_URL = https://planetarycomputer.microsoft.com/api/stac/v1`

---

## Зависимости

```
# Спутниковые данные
pystac-client, planetary-computer, stackstac

# Обработка
numpy, xarray, rasterio, scipy, dask[array], pandas, pyproj

# Визуализация
folium, matplotlib, Pillow, branca

# Веб
streamlit, fastapi, uvicorn, bottle

# CLI
rich

# Отчёты
reportlab

# Сеть
requests, tqdm

# Сборка
pyinstaller

# Опционально (не используются по умолчанию)
# ipywidgets, jupyter, voila
# python-telegram-bot
# copernicusmarine
```

---

## Тестирование

### Что протестировано автоматически

| Тест | Результат |
|------|-----------|
| Синтаксис 18 .py файлов | PASS |
| Импорты всех модулей | PASS |
| Config пороги (FDI=0.01, NDVI=0.2, PI=0.48, MIN_CLUSTER=5) | PASS |
| DN threshold > 100 | PASS |
| DriftResult.distance_km_72h | PASS |
| simulate_drift_multi | PASS |
| confidence_to_rgba | PASS |
| Pipeline интеграция (Средиземное, 10 дней, 16 снимков) | PASS, 222с |
| PNG генерация | PASS, 238KB |
| HTML Folium карта | PASS, 1.1MB |
| PDF отчёт | PASS, 498KB |
| API /health, /presets | PASS |
| Lite Web /health, / (3.2KB) | PASS |
| Lite GUI /health, / (11KB) | PASS |
| telegram_bot.py удалён | PASS |

### Как запустить тесты

```bash
cd /root/ecohack

# Синтаксис
for f in core/*.py apps/*.py viz/*.py config.py build_exe.py; do
  python3 -c "import ast; ast.parse(open('$f').read())" && echo "OK: $f"
done

# Импорты
python3 -c "from core.processor import run_pipeline; print('OK')"

# Полный pipeline (нужен интернет, 2-4 мин)
python3 apps/cli.py --preset med --days 3 --no-html --no-png

# JSON вывод
python3 apps/cli.py --preset med --days 1 --json 2>/dev/null | python3 -m json.tool

# Серверы
python3 apps/api.py &              # порт 8000
python3 apps/lite_web.py &         # порт 8088
python3 apps/lite_gui.py &         # порт 8090
streamlit run apps/streamlit_app.py  # порт 8501
```

---

## Известные ограничения

### Данные
- **Sentinel-2 покрывает в основном сушу**. В открытом океане (Pacific Garbage Patch) снимки раз в ~6 месяцев. Прибрежные моря (Средиземное, Чёрное, Балтийское) — каждые 5 дней.
- Первый запуск скачивает ~100-500 МБ спутниковых тайлов (1-3 мин на хорошем интернете).

### Алгоритм
- Stokes drift — приближение 1.3% от скорости течения (не волновая физика).
- Дрейф не учитывает береговую линию (частицы могут "уплыть" на сушу).
- Временные ряды могут давать несогласованные результаты при смене UTM зон.
- Otsu на чистом океане без мусора может дать ложно-низкий порог (компенсируется floor=0.02).

### UI
- Leaflet в lite_gui загружается с CDN (нужен интернет для карты, но не для анализа).
- Tile layers (Esri, CartoDB, OSM) требуют интернет для фоновой карты.
- lite_web блокирующий (Bottle однопоточный), анализ 1-3 мин без прогресса.

---

## Что можно улучшить далее

### Алгоритм (приоритет высокий)
- [ ] Beaching detection — не давать частицам дрейфа уходить на сушу
- [ ] Stokes drift из ERA5/Open-Meteo wave data вместо приближения
- [ ] Итеративная коррекция маршрута (сейчас 1 итерация)
- [ ] Deduplication сцен из перекрывающихся тайлов
- [ ] Временная нормализация облачности в timeseries (plastic % от чистой площади)

### UI (приоритет средний)
- [ ] Бандл Leaflet + тайлов локально для полного offline
- [ ] PWA manifest для установки на планшет
- [ ] Режим высокой контрастности (солнце на палубе)
- [ ] Next satellite pass forecast
- [ ] Слой Саргассума (показать что отфильтровано как "не пластик")
- [ ] Кривая эффективности маршрута (собранный пластик vs км)
- [ ] FDI anomaly map визуализация (когда temporal включён)
- [ ] Ветровые вектора на карте дрейфа

### Инфраструктура
- [ ] Тесты (pytest) — unit-тесты для indices, drift, route
- [ ] CI/CD пайплайн
- [ ] Docker образ
- [ ] Windows .exe сборка (нужна Windows машина)
- [ ] Кэш спутниковых тайлов на диск (не скачивать повторно)

### Научные ссылки
- Biermann et al. (2020) *Scientific Reports* 10:5364 — FDI
- Kikaki et al. (2020) *Remote Sensing* 12:2648 — PI
- Themistocleous et al. (2020) *Remote Sensing* 12:16 — методология детекции
- McFeeters (1996) *Int. J. Remote Sensing* 17:7 — NDWI
- Hedley et al. (2005) *Remote Sensing of Environment* 93:3 — sun glint correction
