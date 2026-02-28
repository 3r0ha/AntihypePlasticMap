# antihype — Карта пластика

Система детекции скоплений морского пластика по спутниковым снимкам Sentinel-2 с прогнозом дрейфа и построением оптимального маршрута перехвата.

Разработана для экспедиции Фёдора Конюхова в рамках хакатона EcoHack командой **antihype**.

---

## Оглавление

- [Обзор проекта](#обзор-проекта)
- [Архитектура](#архитектура)
- [Научная основа](#научная-основа)
- [Установка и запуск](#установка-и-запуск)
- [Интерфейсы](#интерфейсы)
- [API](#api)
- [CLI](#cli)
- [Конфигурация](#конфигурация)
- [Структура проекта](#структура-проекта)
- [Пайплайн обработки](#пайплайн-обработки)
- [Модули](#модули)
- [Визуализация](#визуализация)
- [Docker-деплой](#docker-деплой)
- [Экспорт данных](#экспорт-данных)
- [Зависимости](#зависимости)
- [Ссылки](#ссылки)

---

## Обзор проекта

**antihype** — полнофункциональная платформа для обнаружения плавающего пластика в океане. Система автоматически:

1. Загружает мультиспектральные снимки **Sentinel-2 L2A** через Microsoft Planetary Computer
2. Вычисляет **FDI** (Floating Debris Index) и каскад дополнительных индексов
3. Выделяет **горячие точки** (кластеры пластика) с субпиксельной оценкой уверенности
4. Прогнозирует **дрейф** обнаруженного пластика на 24–168 часов (ансамблевая лагранжева модель, 30 частиц, метод Рунге-Кутты 4-го порядка)
5. Строит **оптимальный маршрут** для плота через дрейфующие скопления (greedy + 2-opt)
6. Генерирует **PDF-отчёт**, интерактивные карты, GeoJSON и другие форматы экспорта

### Ключевые возможности

| Возможность | Описание |
|---|---|
| Мультииндексный анализ | FDI, FAI, PI, NDVI, NDWI, MNDWI с адаптивным порогом Otsu |
| Маскирование облаков | SCL (Scene Classification Layer) + NDWI подтверждение воды |
| Фильтрация блеска | Детекция солнечного блика (Hedley et al. 2005) |
| Прогноз дрейфа | Open-Meteo + HYCOM + синтетический fallback, 30 частиц, RK4 |
| Маршрутизация | Drift-aware greedy nearest-neighbor + 2-opt оптимизация |
| Темпоральный анализ | Тренды FDI по нескольким временным окнам, линейная регрессия |
| Субпиксельная уверенность | Линейная интерполяция FDI → доля пластика в пикселе |
| 6 интерфейсов | Vue dashboard, Streamlit, CLI, Rich CLI, Lite GUI, Lite Web |
| PDF-отчёт | Карта FDI, гистограмма, таблицы хотспотов и маршрута |
| GeoJSON-векторизация | Растровая маска пластика → полигоны GeoJSON |
| Альтернативные источники | Sentinel-3 OLCI, MODIS Terra, Copernicus CDSE |

---

## Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│                     NGINX (порт 9090)                        │
│              Reverse Proxy + gzip-сжатие                     │
├──────────────────────┬───────────────────────────────────────┤
│   Vue Frontend       │            FastAPI Backend            │
│   (порт 80)          │            (порт 8000)                │
│                      │                                       │
│  ┌────────────────┐  │  ┌─────────────────────────────────┐  │
│  │ MapView        │  │  │ POST /analyze (async + polling) │  │
│  │ Sidebar        │  │  │ POST /drift                     │  │
│  │ MetricCards    │  │  │ POST /route                     │  │
│  │ DriftPanel     │  │  │ GET  /presets                   │  │
│  │ RoutePanel     │  │  │ GET  /health                    │  │
│  │ TemporalPanel  │  │  │ GET  /analyze/{job_id}          │  │
│  │ IndicesPanel   │  │  └─────────┬───────────────────────┘  │
│  │ ExportPanel    │  │            │                           │
│  └────────────────┘  │  ┌─────────▼───────────────────────┐  │
│                      │  │        Core Pipeline             │  │
│                      │  │  data_loader → cloud_mask →      │  │
│                      │  │  indices → processor →           │  │
│                      │  │  currents → drift → route →      │  │
│                      │  │  report + timeseries             │  │
│                      │  └─────────┬───────────────────────┘  │
│                      │            │                           │
│                      │  ┌─────────▼───────────────────────┐  │
│                      │  │  Microsoft Planetary Computer    │  │
│                      │  │  Open-Meteo · HYCOM ERDDAP      │  │
│                      │  └─────────────────────────────────┘  │
└──────────────────────┴───────────────────────────────────────┘
```

**Стек технологий:**
- **Backend:** Python 3.10, FastAPI, Uvicorn, NumPy, xarray, dask, scipy, stackstac
- **Frontend:** Vue 3 (Composition API, `<script setup>`), Vite 5, Leaflet 1.9
- **Визуализация:** Matplotlib, Folium, ReportLab (PDF)
- **Данные:** Sentinel-2 L2A (Microsoft Planetary Computer STAC API)
- **Океанография:** Open-Meteo Marine API, HYCOM via NOAA ERDDAP
- **Деплой:** Docker Compose (3 контейнера: API + Frontend + Nginx)

---

## Научная основа

### Floating Debris Index (FDI)

Основной индекс обнаружения плавающего пластика по методу **Biermann et al. (2020)**:

```
FDI = R(B8A) - R'(B8A)

где R'(B8A) = R(B6) + [R(B11) - R(B6)] × (λ_B8A - λ_B6) / (λ_B11 - λ_B6)
```

| Канал | Длина волны | Роль |
|-------|-------------|------|
| B6 | 740 нм | Red Edge 2 (базовая линия) |
| B8A | 865 нм | NIR narrow (целевой) |
| B11 | 1610 нм | SWIR 1 (базовая линия) |

Пластик создаёт аномалию в NIR (865 нм): отражение выше линейной интерполяции между Red Edge и SWIR. Положительный FDI указывает на плавающий материал.

**Источник:** Biermann et al. (2020), *Scientific Reports* 10, 5364. DOI: [10.1038/s41598-020-62298-z](https://doi.org/10.1038/s41598-020-62298-z)

### Каскад дополнительных индексов

| Индекс | Формула | Назначение |
|--------|---------|------------|
| **FAI** | B08 - [B04 + (B11 - B04) × slope] | Floating Algae Index (Hu 2009) — водоросли + пластик |
| **PI** | B08 / (B08 + B04) | Plastic Index (Kikaki et al. 2020) — соотношение NIR/Red |
| **NDVI** | (B08 - B04) / (B08 + B04) | Фильтрация водорослей (NDVI > 0.2 = не пластик) |
| **NDWI** | (B03 - B08) / (B03 + B08) | Подтверждение водной поверхности (> 0 = вода) |
| **MNDWI** | (B03 - B12) / (B03 + B12) | Модифицированный NDWI (Xu 2006), B12 @ 2190 нм |

### Адаптивный порог

Гибридный порог FDI: `max(Otsu, μ + 3σ, floor)`, где:
- **Otsu** — автоматическая бимодальная сегментация по гистограмме FDI (256 бинов)
- **μ + 3σ** — статистический порог (3 сигмы от среднего по водным пикселям)
- **floor** — абсолютный минимум 0.005 (защита от ложных срабатываний)

### Условия детекции пластика

Пиксель считается пластиком, если проходит **все** условия:

1. FDI > адаптивный порог
2. NDWI > 0 (водный пиксель)
3. NDVI < 0.2 (не водоросли)
4. PI > 0.48 (соотношение NIR/Red характерно для пластика)
5. NIR < 0.3 (не земля/облако)
6. SWIR < 0.25 (не земля/облако)
7. SCL = 6 (класс «вода» по Scene Classification Layer)
8. Не SCL 4, 5, 7 (земля, кустарник, снег)
9. Не солнечный блик (Hedley et al. 2005)
10. Кластер >= 3 пикселей (морфологическая фильтрация)

### Модель дрейфа

Ансамблевая лагранжева модель с 30 частицами:

```
v_total = v_ocean + v_stokes + v_wind_leeway

v_stokes = 1.3% × v_ocean          (дрейф Стокса)
v_wind_leeway = 2.5% × v_wind_10m  (парусность пластика, Isobe 2014)
```

- **Интегрирование:** Рунге-Кутта 4-го порядка (RK4), шаг dt = 0.5 ч
- **Ансамбль:** 30 частиц с +/-5% возмущением скорости течения
- **Неопределённость:** 1-сигма пространственного разброса ансамбля
- **Источники данных:** Open-Meteo Marine API -> HYCOM ERDDAP -> синтетическая модель (fallback)

### Маршрутизация

Оптимальный маршрут для плота (~2 узла = 3.7 км/ч) через дрейфующие скопления:

1. **Приоритизация:** score = FDI_max * (1 + area_km2)
2. **Жадный выбор:** ближайший по расстоянию с учётом приоритета
3. **Drift-aware ETA:** позиция хотспота пересчитывается с учётом дрейфа за время пути
4. **2-opt оптимизация:** улучшение порядка обхода путём перестановки рёбер (до 100 итераций)

---

## Установка и запуск

### Требования

- Python 3.10+
- Node.js 18+ (для фронтенда)
- Docker + Docker Compose (для серверного деплоя)

### Быстрый старт (Docker)

```bash
git clone <repo-url>
cd ecohack
docker compose up --build -d
```

Приложение доступно на `http://localhost:9090`

### Локальная разработка

```bash
# Backend
pip install -r requirements.txt

# Запуск API
python -m uvicorn apps.api:app --host 0.0.0.0 --port 8000

# Frontend (в отдельном терминале)
cd frontend
npm install
npm run dev    # http://localhost:5173, проксирует /api -> localhost:8000
```

### Альтернативные интерфейсы

```bash
# Streamlit (полный интерфейс)
streamlit run apps/streamlit_app.py --server.port 8501

# Rich CLI (красивый терминал)
python apps/cli_rich.py --preset kochi

# Стандартный CLI
python apps/cli.py --lat 10.0 --lon 76.3 --days 10

# Lite GUI (Bottle + Leaflet, ~50KB)
python apps/lite_gui.py    # http://localhost:8090

# Lite Web (ультралёгкий, без JS)
python apps/lite_web.py    # http://localhost:8088
```

---

## Интерфейсы

### 1. Vue Dashboard (основной)

Полнофункциональная SPA на Vue 3 + Leaflet с тёмной морской темой.

**Режимы:**
- **Лёгкая версия** (~50 КБ трафика) — карта, хотспоты, дрейф, маршрут
- **Полная версия** (~2-5 МБ) — спектральные индексы, карта уверенности, Folium HTML, PDF

**Вкладки:**

| Вкладка | Содержимое |
|---------|------------|
| Карта | Leaflet: Esri Satellite / CartoDB Dark, хотспоты, дрейф-траектории, маршрут, легенда, масштаб, координаты курсора |
| Индексы | 6-панельная визуализация (FDI, маска, облака, гистограмма, пирог, метрики), таблица сравнения индексов |
| Дрейф | KPI-карточки (смещение 24/48ч, скорость, направление), мини-карта с траекторией, таблица позиций, standalone пересчёт |
| Маршрут | Hero-карточка «следующая точка» (курс, дистанция, ETA), KPI, мини-карта с маршрутом, навигационная таблица, standalone пересчёт |
| Тренды | SVG-график FDI (mean/max) по датам, таблица данных |
| Экспорт | Кнопки скачивания: JSON, GeoJSON (хотспоты/маршрут), PNG, HTML, PDF |

**Интерактивность:**
- Клик по карте -> установка координат
- Координаты курсора в реальном времени
- Визуализация буферной зоны (пунктирный прямоугольник)
- Клик по хотспоту в сайдбаре -> zoom на карте
- Standalone пересчёт дрейфа/маршрута без повторного анализа

### 2. Streamlit

Полнофункциональное приложение с 6 вкладками (Карта, Индексы, Дрейф, Маршрут, Отчёт, Экспорт). Folium-карты, matplotlib-графики, PDF-генерация, экспорт в CSV/GeoJSON/HTML/PNG/JSON.

### 3. CLI

Два варианта: стандартный (`cli.py`) и с Rich-форматированием (`cli_rich.py`).

```bash
# Базовый запуск
python apps/cli.py --preset kochi --days 10 --route

# С координатами
python apps/cli.py --lat 10.0 --lon 76.3 --buffer 0.5 --cloud 85

# JSON-вывод
python apps/cli.py --preset mumbai --json

# Rich CLI (красивые таблицы)
python apps/cli_rich.py --preset singapore --temporal
```

**Флаги CLI:**

| Флаг | Описание | По умолчанию |
|------|----------|-------------|
| `--preset` | Пресет локации (kochi, mumbai, singapore и др.) | — |
| `--lat`, `--lon` | Координаты (альтернатива пресету) | — |
| `--days` | Период поиска снимков (дни) | 10 |
| `--buffer` | Буферная зона (градусы) | 0.15 |
| `--cloud` | Макс. облачность (%) | 90 |
| `--output` | Директория вывода | outputs |
| `--temporal` | Темпоральная аномалия | выкл. |
| `--no-drift` | Без дрейф-коррекции | вкл. |
| `--route` | Построить маршрут | выкл. |
| `--json` | Вывод в JSON | выкл. |
| `-v` | Подробный лог | выкл. |

### 4. Lite GUI

Однофайловое приложение (Bottle + Leaflet) для PyInstaller. Полный интерфейс с картой, хотспотами, GPS-геолокацией в ~200 КБ. Порт 8090.

### 5. Lite Web

Ультралёгкий (<50 КБ на страницу) HTML-интерфейс без JavaScript. Оптимален для спутникового интернета. Порт 8088.

---

## API

Все эндпоинты доступны по базовому пути `/api/` (через nginx) или напрямую на порту 8000.

### `GET /health`

Проверка доступности сервера.

```json
{"status": "ok", "timestamp": "2026-02-28T12:00:00", "version": "2.0.0"}
```

### `GET /presets`

Список доступных локаций (9 пресетов).

```json
{
  "presets": [
    {"name": "Кочи, Индия", "lat": 10.0, "lon": 76.3},
    {"name": "Мумбаи, Индия", "lat": 19.05, "lon": 72.85},
    {"name": "Сингапурский пролив", "lat": 1.3, "lon": 103.8},
    {"name": "Дурбан, ЮАР", "lat": -29.85, "lon": 31.05},
    {"name": "Средиземное море", "lat": 37.0, "lon": 13.0},
    {"name": "Чёрное море", "lat": 42.5, "lon": 35.0},
    {"name": "Ченнай, Индия", "lat": 13.1, "lon": 80.3},
    {"name": "Джакарта, Индонезия", "lat": -6.1, "lon": 106.85},
    {"name": "Осака, Япония", "lat": 35.15, "lon": 136.9}
  ]
}
```

### `POST /analyze`

Основной анализ. Поддерживает синхронный и асинхронный режим.

**Тело запроса:**

```json
{
  "lat": 10.0,
  "lon": 76.3,
  "days_back": 10,
  "buffer_deg": 0.5,
  "max_cloud_cover": 85,
  "include_drift": true,
  "include_route": true,
  "enable_temporal": false,
  "include_visuals": false,
  "wind_u": 0.0,
  "wind_v": 0.0,
  "async_mode": true,
  "resolution": 60,
  "max_scenes": 5
}
```

**Параметры запроса:**

| Параметр | Тип | Диапазон | По умолчанию | Описание |
|----------|-----|----------|-------------|----------|
| `lat` | float | -90..90 | — | Широта центра поиска |
| `lon` | float | -180..180 | — | Долгота центра поиска |
| `days_back` | int | 1..30 | 3 | Период поиска снимков (дни) |
| `buffer_deg` | float | 0.1..3.0 | 0.5 | Буферная зона (градусы) |
| `max_cloud_cover` | int | 10..100 | 85 | Макс. облачность (%) |
| `include_drift` | bool | — | true | Включить прогноз дрейфа |
| `include_route` | bool | — | true | Построить маршрут |
| `enable_temporal` | bool | — | false | Темпоральная аномалия |
| `include_visuals` | bool | — | false | Генерация PNG/HTML/PDF (полный режим) |
| `resolution` | int | 10..500 | 60 | Разрешение пикселя (метры) |
| `max_scenes` | int | 1..10 | 5 | Макс. количество снимков |
| `async_mode` | bool | — | false | Асинхронный режим с polling |
| `wind_u` | float | — | 0.0 | Компонента ветра U (м/с, восточная) |
| `wind_v` | float | — | 0.0 | Компонента ветра V (м/с, северная) |

**Ответ (async_mode=true):**

```json
{"job_id": "uuid-string"}
```

**Polling:** `GET /analyze/{job_id}`

```json
{
  "status": "done",
  "result": {
    "success": true,
    "scenes_found": 3,
    "scene_dates": ["2026-02-20", "2026-02-23", "2026-02-25"],
    "stats": {
      "plastic_area_km2": 0.045,
      "plastic_coverage_pct": 0.12,
      "fdi_max": 0.0234,
      "fdi_mean": 0.0012,
      "fdi_median": 0.0008,
      "fdi_p95": 0.0089,
      "fdi_p99": 0.0156,
      "fdi_threshold_used": 0.0089,
      "cloud_coverage_pct": 15.3,
      "confidence_mean": 0.72,
      "confidence_max": 0.95,
      "total_valid_pixels": 125000,
      "plastic_pixels": 42,
      "total_area_km2": 450.0
    },
    "hotspots": [
      {
        "lat": 10.0123,
        "lon": 76.3456,
        "fdi_max": 0.0234,
        "area_km2": 0.015,
        "n_pixels": 12,
        "confidence_mean": 0.68,
        "confidence_max": 0.95
      }
    ],
    "hotspots_drift_corrected": [...],
    "drift": [
      {
        "hotspot": {"lat": 10.0123, "lon": 76.3456},
        "origin": {"lat": 10.0123, "lon": 76.3456},
        "position_24h": {"lat": 10.05, "lon": 76.28},
        "position_48h": {"lat": 10.11, "lon": 76.25},
        "distance_km_24h": 6.2,
        "distance_km_48h": 13.8,
        "current_speed_ms": 0.15,
        "current_direction_deg": 215.0,
        "current_source": "open_meteo",
        "is_synthetic": false
      }
    ],
    "route": {
      "waypoints": [
        {
          "lat": 10.1, "lon": 76.2,
          "label": "WP1",
          "bearing_deg": 315.0,
          "distance_km": 14.2,
          "eta_hours": 3.8,
          "fdi_max": 0.02,
          "area_km2": 0.5
        }
      ],
      "total_distance_km": 14.2,
      "total_eta_hours": 3.8,
      "n_waypoints": 1
    },
    "temporal": [...],
    "warnings": [],
    "processing_time_sec": 8.5
  }
}
```

### `POST /drift`

Standalone-прогноз дрейфа для заданной точки.

```json
// Запрос
{"lat": 10.0, "lon": 76.3, "hours": 72}

// Ответ
{
  "origin": {"lat": 10.0, "lon": 76.3},
  "position_24h": {"lat": 10.05, "lon": 76.28},
  "position_48h": {"lat": 10.11, "lon": 76.25},
  "distance_km_24h": 6.2,
  "distance_km_48h": 13.8,
  "current_speed_ms": 0.15,
  "current_direction_deg": 215.0,
  "current_source": "open_meteo",
  "is_synthetic": false
}
```

### `POST /route`

Standalone-построение маршрута через хотспоты.

```json
// Запрос
{
  "raft_lat": 10.0,
  "raft_lon": 76.3,
  "hotspots": [
    {"lat": 10.1, "lon": 76.2, "fdi_max": 0.02, "area_km2": 0.5}
  ],
  "max_waypoints": 10
}

// Ответ
{
  "waypoints": [
    {
      "lat": 10.1, "lon": 76.2,
      "label": "WP1",
      "bearing_deg": 315.0,
      "distance_km": 14.2,
      "eta_hours": 3.8,
      "fdi_max": 0.02,
      "area_km2": 0.5
    }
  ],
  "total_distance_km": 14.2,
  "total_eta_hours": 3.8,
  "n_waypoints": 1
}
```

---

## Конфигурация

### Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `ECOHACK_BUFFER` | 0.15 | Буферная зона поиска (градусы) |
| `ECOHACK_DAYS` | 10 | Период поиска снимков (дни) |
| `ECOHACK_RESOLUTION` | 200 | Разрешение пикселя (метры) |

### Пресеты локаций

| Ключ | Координаты | Название |
|------|-----------|----------|
| `kochi` | 10.0°N, 76.3°E | Кочи, Индия |
| `mumbai` | 19.05°N, 72.85°E | Мумбаи, Индия |
| `singapore` | 1.3°N, 103.8°E | Сингапурский пролив |
| `durban` | 29.85°S, 31.05°E | Дурбан, ЮАР |
| `med` | 37.0°N, 13.0°E | Средиземное море |
| `black_sea` | 42.5°N, 35.0°E | Чёрное море |
| `chennai` | 13.1°N, 80.3°E | Ченнай, Индия |
| `jakarta` | 6.1°S, 106.85°E | Джакарта, Индонезия |
| `osaka` | 35.15°N, 136.9°E | Осака, Япония |

### Пороги детекции

| Параметр | Значение | Описание |
|----------|---------|----------|
| `FDI_PLASTIC_THRESHOLD` | 0.015 | Порог FDI (Biermann 2020) |
| `FDI_ABSOLUTE_FLOOR` | 0.005 | Минимальный порог FDI |
| `NDWI_WATER_THRESHOLD` | 0.0 | Порог NDWI (>0 = вода) |
| `NDVI_MAX_THRESHOLD` | 0.2 | Макс. NDVI (фильтр водорослей) |
| `PI_PLASTIC_THRESHOLD` | 0.48 | Порог Plastic Index |
| `NIR_MAX_REFLECTANCE` | 0.3 | Макс. отражение NIR |
| `SWIR_MAX_REFLECTANCE` | 0.25 | Макс. отражение SWIR |
| `MIN_CLUSTER_PIXELS` | 3 | Мин. пикселей в кластере |

---

## Структура проекта

```
ecohack/
├── config.py                    # Глобальная конфигурация, пресеты, пороги
├── requirements.txt             # Python-зависимости (53 пакета)
├── Dockerfile                   # Docker-образ API (Python 3.10 + GDAL)
├── docker-compose.yml           # Оркестрация 3 контейнеров
├── nginx.conf                   # Reverse proxy + gzip
├── .dockerignore                # Исключения из Docker-контекста
│
├── core/                        # Ядро обработки
│   ├── __init__.py              # Экспорт run_pipeline
│   ├── data_loader.py           # Загрузка Sentinel-2 через Planetary Computer STAC
│   ├── data_loader_s3.py        # Альтернативные источники (Sentinel-3, MODIS, CDSE)
│   ├── cloud_mask.py            # Маскирование облаков (SCL), медианный композит
│   ├── indices.py               # Спектральные индексы (FDI, FAI, PI, NDVI, NDWI, MNDWI)
│   ├── processor.py             # Главный пайплайн (PipelineResult)
│   ├── currents.py              # Океанические течения (Open-Meteo, HYCOM, синтетика)
│   ├── drift.py                 # Лагранжева модель дрейфа (DriftResult)
│   ├── route.py                 # Маршрутизация (RouteResult, 2-opt)
│   ├── report.py                # PDF-отчёт (ReportLab)
│   └── timeseries.py            # Темпоральный анализ трендов (TimeSeriesResult)
│
├── viz/                         # Визуализация
│   ├── __init__.py              # Экспорт make_folium_map, make_static_png
│   ├── maps.py                  # Интерактивные Folium-карты (10+ слоёв)
│   └── plots.py                 # Статические matplotlib PNG (2-4 панели)
│
├── apps/                        # Интерфейсы
│   ├── api.py                   # FastAPI REST API (6 эндпоинтов)
│   ├── cli.py                   # Стандартный CLI (argparse)
│   ├── cli_rich.py              # Rich CLI (красивые таблицы)
│   ├── streamlit_app.py         # Streamlit dashboard (6 вкладок)
│   ├── streamlit_runner.py      # PyInstaller-обёртка для Streamlit
│   ├── lite_gui.py              # Bottle + Leaflet GUI (порт 8090)
│   └── lite_web.py              # Ультралёгкий HTML (порт 8088, <50 КБ)
│
└── frontend/                    # Vue 3 SPA
    ├── package.json             # Vue 3.4, Leaflet 1.9, Vite 5
    ├── vite.config.js           # Прокси /api -> localhost:8000
    ├── index.html               # Точка входа (шрифт Inter)
    ├── Dockerfile               # Multi-stage: Node build -> Nginx serve
    └── src/
        ├── main.js              # Инициализация Vue
        ├── api.js               # Обёртка fetch -> FastAPI (таймауты, polling)
        ├── style.css            # Тёмная морская тема, responsive (768/1024px)
        └── components/
            ├── App.vue           # Главный layout, роутинг вкладок, state
            ├── ModeSelector.vue  # Выбор режима (лёгкий/полный)
            ├── WelcomeScreen.vue # Стартовый экран с описанием и формулой FDI
            ├── Sidebar.vue       # Параметры, пресеты, хотспоты, маршрут
            ├── MapView.vue       # Leaflet карта (хотспоты, дрейф, маршрут, легенда)
            ├── MetricCards.vue   # 8 KPI-карточек поверх карты
            ├── StatusBar.vue     # Футер (статус, предупреждения, время)
            ├── IndicesPanel.vue  # Спектральные индексы (6 графиков)
            ├── DriftPanel.vue    # Дрейф (KPI, карта, таблица, пересчёт)
            ├── RoutePanel.vue    # Маршрут (hero, KPI, карта, таблица, пересчёт)
            ├── TemporalPanel.vue # SVG-тренды FDI (линейный график + таблица)
            └── ExportPanel.vue   # Кнопки экспорта (JSON/GeoJSON/PNG/HTML/PDF)
```

---

## Пайплайн обработки

Последовательность шагов `run_pipeline()`:

```
 1. [10%]  Поиск снимков Sentinel-2 (STAC API, сортировка по облачности)
           ├── Retry: 3 попытки, интервал 2 сек
           ├── Fallback: 90 дней -> all-time + расширенный bbox
           └── Ограничение: max 5 снимков

 2. [20%]  Загрузка спектральных каналов (B03, B04, B06, B08, B8A, B11, B12, SCL)
           ├── stackstac.stack() -> lazy xarray DataArray
           ├── dtype float64 (совместимость с NaN fill_value)
           └── UTM-проекция (автоопределение EPSG)

 3. [30%]  Маскирование облаков (SCL классы 3, 8, 9, 10, 11)
           ├── cloud_cover_fraction() -> фильтрация по порогу 50%
           └── select_least_cloudy() -> выбор лучших снимков

 4. [45%]  Медианный композит (median over time, skipna=True)
           ├── _auto_scale_composite() -> DN -> рефлектанс (0-1)
           └── dask.compute() с retry (3 попытки, 5 сек задержка)

 5. [55%]  Вычисление спектральных индексов
           ├── FDI (Biermann 2020)
           ├── FAI (Hu 2009)
           ├── PI (Kikaki 2020)
           ├── NDVI (фильтр водорослей)
           ├── NDWI (подтверждение воды)
           ├── MNDWI (Xu 2006, если есть B12)
           └── Glint mask (Hedley 2005)

 6. [62%]  Адаптивный порог FDI
           ├── Otsu на водных пикселях (256 бинов)
           ├── mu + 3*sigma по водным пикселям
           └── max(Otsu, mu+3*sigma, floor=0.005)

 7. [70%]  Пластиковая маска
           ├── Мультислойная фильтрация (10 условий)
           ├── Морфологическое открытие (binary_opening)
           └── Удаление кластеров < 3 пикселей

 8. [75%]  Субпиксельная карта уверенности
           └── Линейная интерполяция FDI: threshold -> 0, p99 -> 1

 9. [78%]  Темпоральная базовая линия (если enable_temporal)
           ├── 90-дневный медианный FDI
           └── Аномалия = текущий FDI - базовый FDI

10. [85%]  Поиск горячих точек
           ├── scipy.ndimage.label (connected components)
           ├── Топ-10 кластеров по FDI_max
           └── Площадь через UTM-проекцию (pyproj)

11. [90%]  Дрейф-коррекция хотспотов (если enable_drift)
           ├── Расчёт времени от съёмки
           ├── Получение течений (Open-Meteo -> HYCOM -> синтетика)
           └── Коррекция позиции на dt (макс. 72ч)

12. [95%]  Статистика
           ├── Площадь в км²
           ├── Покрытие в %
           ├── FDI: max, mean, median, p95, p99
           └── Облачность в %

13. [100%] Кэширование результата (LRU, max 10, TTL 3600 сек)
```

---

## Модули

### `core/data_loader.py` — Загрузка данных

Загрузка мультиспектральных снимков Sentinel-2 L2A через Microsoft Planetary Computer STAC API.

**Функции:**
- `make_bbox(lat, lon, buffer)` — ограничивающий прямоугольник [W, S, E, N] с clamping координат
- `make_date_range(days_back)` — ISO-строка диапазона дат для STAC
- `search_scenes(lat, lon, days_back, buffer, max_cloud_cover)` — поиск снимков (3 retry, fallback 90 дней -> all-time)
- `load_bands(items, lat, lon, buffer, resolution, max_items)` — lazy-загрузка через stackstac (float64, UTM)
- `get_sentinel2_data(lat, lon, ...)` — обёртка: поиск + загрузка, возвращает (xarray.DataArray, items)
- `get_scene_metadata(items)` — метаданные: id, дата, облачность, платформа

**Каналы:** B03 (560нм), B04 (665нм), B06 (740нм), B08 (842нм), B8A (865нм), B11 (1610нм), B12 (2190нм), SCL

### `core/data_loader_s3.py` — Альтернативные источники

Поддержка дополнительных спутниковых данных для открытого океана.

- `search_sentinel3(lat, lon, ...)` — Sentinel-3 OLCI WFR L2 (300 м, ежедневно)
- `compute_fdi_s3(bands)` — AFAI для Sentinel-3 (681/865/1020 нм)
- `search_modis_earthdata(lat, lon, ...)` — MODIS Terra MOD09GQ (250 м, NASA CMR API)
- `search_copernicus_cdse(lat, lon, ...)` — Copernicus CDSE (OData API)
- `get_available_data_sources(lat, lon, ...)` — проверка доступности всех источников

### `core/cloud_mask.py` — Маски облаков

Маскирование облачных пикселей по SCL (Scene Classification Layer) Sentinel-2.

- `apply_cloud_mask(stack)` — маскирование классов 3 (тени), 8-9 (облака), 10 (дымка), 11 (снег)
- `cloud_cover_fraction(cloud_mask)` — доля облачности 0.0-1.0 по каждому снимку
- `select_least_cloudy(stack, cloud_mask, max_fraction)` — фильтрация снимков по облачности
- `make_composite(masked_stack, cloud_mask)` — медианный композит (skipna=True)

### `core/indices.py` — Спектральные индексы

18 функций для вычисления индексов, масок и статистики.

**Индексы:**
- `compute_fdi(composite)` — Floating Debris Index (B8A/B6/B11, Biermann 2020)
- `compute_fai(composite)` — Floating Algae Index (B04/B08/B11, Hu 2009)
- `compute_pi(composite)` — Plastic Index (B08/B04, Kikaki 2020)
- `compute_ndvi(composite)` — NDVI (B08/B04)
- `compute_ndwi(composite)` — NDWI (B03/B08)
- `compute_ndwi_swir(composite)` — MNDWI (B03/B12, Xu 2006)

**Маски и пороги:**
- `compute_glint_mask(composite)` — маска солнечного блика (Hedley 2005)
- `compute_adaptive_fdi_threshold(fdi, water_mask)` — гибридный порог: max(Otsu, mu+3*sigma, floor)
- `compute_plastic_mask(fdi, ndwi, composite, ndvi, pi, threshold)` — многослойная маска (10 условий)
- `apply_morphological_filter(mask, min_pixels)` — удаление мелких кластеров (scipy.ndimage.label)
- `compute_sargassum_mask(fai, ndvi, ndwi)` — маска водорослей Sargassum

**Анализ:**
- `compute_confidence_map(fdi, plastic_mask, threshold)` — субпиксельная уверенность (0-1)
- `find_hotspots(fdi, plastic_mask, lats, lons, top_n)` — топ-N кластеров (connected components)
- `compute_stats(fdi, plastic_mask, cloud_mask, pixel_size_m)` — статистика (площадь, покрытие, FDI)
- `compute_all_indices(composite)` — все индексы одним вызовом
- `mask_to_geojson(plastic_mask, lats, lons)` — векторизация маски -> GeoJSON FeatureCollection

### `core/processor.py` — Главный пайплайн

Координирует весь процесс обработки от координат до результата.

- `run_pipeline(lat, lon, ...)` -> `PipelineResult` (25+ полей)
  - LRU-кэш (10 записей, TTL 3600 сек)
  - Retry dask.compute() (3 попытки, 5 сек пауза)
  - Progress callback (10-100%)
  - Автомасштабирование DN -> рефлектанс
  - Темпоральная базовая линия (90-дневный медианный FDI)
  - Дрейф-коррекция хотспотов

**PipelineResult** — dataclass с полями: `lat`, `lon`, `fdi`, `ndwi`, `plastic_mask`, `confidence_map`, `cloud_mask`, `glint_mask`, `fdi_anomaly`, `lons`, `lats`, `scenes_found`, `scenes_used`, `scene_dates`, `stats`, `hotspots`, `hotspots_drift_corrected`, `fdi_threshold_used`, `processing_time_sec`, `warnings`

### `core/currents.py` — Океанические течения

Получение данных о течениях и ветре из нескольких источников с приоритетом.

- `get_ocean_currents(lat, lon, buffer)` — приоритет: Open-Meteo -> HYCOM -> синтетика
- **Open-Meteo:** течения (ocean_current_velocity/direction) + 10м ветер на сетке, среднее за 24ч
- **HYCOM:** NOAA CoastWatch ERDDAP, только течения
- **Синтетика:** модель гира + гауссов шум +/-5%, ветер ~5 м/с (fallback)

Константы: `PLASTIC_WIND_LEEWAY = 0.025` (2.5% от скорости ветра, Isobe 2014)

### `core/drift.py` — Модель дрейфа

Ансамблевая лагранжева модель прогноза дрейфа пластика.

- `simulate_drift(lat, lon, currents, hours, dt_hours)` -> `DriftResult`
  - 30 частиц с +/-5% возмущениями
  - RK4-интегрирование, шаг 0.5ч
  - Позиции на 24/48/72ч с 1-sigma неопределённостью
- `simulate_drift_multi(hotspots, currents)` — дрейф для нескольких хотспотов (макс. 5)
- `haversine_km(lat1, lon1, lat2, lon2)` — расстояние по большому кругу

**DriftResult** — dataclass: `origin`, `trajectory`, `positions_24h/48h/72h`, `uncertainty_km_*`, `distance_km_*`, `current_speed_ms`, `current_direction_deg`, `source`, `is_synthetic`

### `core/route.py` — Маршрутизация

Drift-aware маршрутизация для плота через пластиковые скопления.

- `plan_route(start_lat, start_lon, hotspots, currents, max_hotspots)` -> `RouteResult`
  - Scoring: FDI_max * (1 + area_km2)
  - Greedy nearest-neighbor + drift-aware ETA
  - 2-opt local search (до 100 итераций)
- `route_to_geojson(route)` — конвертация в GeoJSON (LineString + Points)
- `bearing_deg(lat1, lon1, lat2, lon2)` — начальный курс (0-360°)

**RouteResult** — dataclass: `start_lat/lon`, `waypoints` (list of Waypoint), `total_distance_km`, `total_eta_hours`, `n_hotspots`

**Waypoint** — dataclass: `lat`, `lon`, `label`, `fdi_max`, `area_km2`, `distance_from_prev_km`, `bearing_from_prev_deg`, `eta_hours`, `drift_correction_km`, `priority`

### `core/report.py` — PDF-отчёт

Генерация миссионного PDF-отчёта с картами, таблицами и графиками.

- `generate_pdf_report(...)` -> bytes
  - Карта FDI (через viz.plots.make_static_png)
  - Гистограмма распределения FDI (matplotlib)
  - Таблица параметров миссии
  - Таблица статистики
  - Таблица горячих точек (топ-10)
  - Таблица прогноза дрейфа
  - Навигационная таблица маршрута
  - Раздел методологии
  - Шрифт DejaVuSans для кириллицы, fallback Helvetica

### `core/timeseries.py` — Темпоральный анализ

Мульти-темпоральный анализ трендов пластикового загрязнения.

- `run_timeseries(lat, lon, n_periods, days_per_period, buffer)` -> `TimeSeriesResult`
  - N временных окон по M дней
  - Линейная регрессия (numpy.polyfit)
  - `trend_direction`: stable / increasing / decreasing
  - `coverage_change_pct`: разница покрытия (конец - начало)

**TimeSeriesFrame** — dataclass: `date`, `fdi`, `plastic_mask`, `plastic_coverage_pct`, `plastic_area_km2`, `fdi_mean`, `fdi_max`, `cloud_coverage_pct`, `scenes_found`, `valid`

---

## Визуализация

### `viz/maps.py` — Интерактивные карты (Folium)

Генерирует многослойную HTML-карту:

| Слой | Описание |
|------|----------|
| Esri Satellite | Спутниковый базовый слой |
| CartoDB Dark | Тёмный базовый слой |
| OpenStreetMap | Стандартный базовый слой |
| RGB Composite | True Color (B4/B3/B2) |
| FDI Index | Адаптивная p2-p98 нормализация, colorbar |
| Cloud Mask | Серый overlay |
| Plastic Detection | Маркеры пластиковых пикселей |
| Hotspots | Красные круги (радиус ~ area_km2), до 15 |
| Drift-corrected | Оранжевые маркеры |
| Drift Trajectory | Полилиния + 24/48/72ч позиции + круги неопределённости |
| Route | Waypoints + полилиния |
| Confidence Map | Зелёный -> жёлтый -> красный overlay |

Дополнительно: легенда FDI (градиент), информационная панель со статистикой, fullscreen, координаты курсора.

### `viz/plots.py` — Статические карты (matplotlib)

Генерирует PNG (2-4 панели):

1. **True Color RGB** (B4/B3/B2) — если есть rgb_composite
2. **FDI Index** — p2-p98 нормализация + colorbar
3. **Маска пластика** — красный на синем фоне + облака серым
4. **Карта уверенности** — RdYlGn_r colormap

Заголовок с вердиктом ("Обнаружены скопления пластика" / "Зона чистая"), футер со статистикой.

Тёмная тема (#0a1628), шкала масштаба, маркеры хотспотов.

---

## Docker-деплой

### Контейнеры

| Контейнер | Образ | Порт | Назначение |
|-----------|-------|------|------------|
| `api` | python:3.10-slim + GDAL | 8000 | FastAPI backend |
| `frontend` | node:20-alpine -> nginx:alpine | 80 | Vue SPA (multi-stage build) |
| `nginx` | nginx:alpine | 9090->80 | Reverse proxy |

### Ресурсы и мониторинг

```yaml
api:
  deploy:
    resources:
      limits:
        memory: 4G
        cpus: "2.0"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
```

### Nginx

- Проксирование: `/` -> frontend (Vue SPA), `/api/` -> API backend
- gzip-сжатие: JSON, HTML, CSS, JS (мин. 256 байт)
- Таймаут API-запросов: 300 сек
- `client_max_body_size`: 1 МБ

### Команды

```bash
# Сборка и запуск
docker compose up --build -d

# Логи
docker compose logs -f api
docker compose logs -f frontend

# Остановка
docker compose down

# Пересборка одного сервиса
docker compose up --build -d api
```

---

## Экспорт данных

| Формат | Описание | Доступность |
|--------|----------|-------------|
| JSON | Полные данные анализа (без визуализаций) | Все интерфейсы |
| GeoJSON (хотспоты) | FeatureCollection с Point features (fdi_max, area_km2) | Все интерфейсы |
| GeoJSON (маршрут) | LineString + Point waypoints (bearing, distance, ETA) | Все интерфейсы |
| GeoJSON (маска) | Polygon features из растровой маски пластика | API (полный режим) |
| PNG | 2-4 панельный статический обзор (FDI, маска, RGB, уверенность) | Полный режим |
| HTML | Интерактивная Folium-карта (10+ слоёв) | Полный режим |
| PDF | Миссионный отчёт (карта, гистограмма, таблицы, методология) | Полный режим |
| CSV | FDI-значения (выборка 50k пикселей) | Streamlit |

---

## Зависимости

### Python (53 пакета)

| Категория | Пакеты |
|-----------|--------|
| Спутниковые данные | pystac-client, planetary-computer, stackstac, rasterio, pyproj |
| Обработка данных | numpy, xarray, dask[array], scipy, pandas |
| Визуализация | matplotlib, folium, branca, Pillow |
| Веб | fastapi, uvicorn, streamlit, bottle |
| Отчёты | reportlab |
| CLI | rich, tqdm |
| Утилиты | requests |
| Упаковка | pyinstaller |

### Frontend (npm)

| Категория | Пакеты |
|-----------|--------|
| Runtime | vue 3.4, leaflet 1.9, @vue-leaflet/vue-leaflet 0.10 |
| Dev | @vitejs/plugin-vue 5.0, vite 5.4 |

---

## Ссылки

1. Biermann L. et al. (2020) *Finding Plastic Patches in Coastal Waters using Optical Satellite Data.* Scientific Reports 10, 5364. [DOI: 10.1038/s41598-020-62298-z](https://doi.org/10.1038/s41598-020-62298-z)
2. Hu C. (2009) *A novel ocean color index to detect floating algae in the global oceans.* Remote Sensing of Environment.
3. Kikaki A. et al. (2020) *MARIDA: A benchmark for Marine Debris detection from Sentinel-2 remote sensing data.* PLOS ONE.
4. Xu H. (2006) *Modification of normalised difference water index (NDWI) to enhance open water features.* International Journal of Remote Sensing.
5. Hedley J. D. et al. (2005) *Simple and robust removal of sun glint for mapping shallow-water benthos.* International Journal of Remote Sensing.
6. Isobe A. et al. (2014) *Selective transport of microplastics and mesoplastics by drifting in coastal waters.* Marine Pollution Bulletin.

---

## Данные

**Microsoft Planetary Computer** — бесплатный каталог спутниковых данных:
- Не требует регистрации и API-ключей
- Sentinel-2 L2A (атмосферно скорректированные снимки, 10-60м)
- STAC API + автоматическая подпись URLs
- Обработка данных на стороне сервера через stackstac/dask

**Open-Meteo** — бесплатный API океанических данных:
- Морские течения (скорость, направление)
- Ветер на 10м (скорость, направление)
- Без API-ключа, лимит запросов

**HYCOM** — гидродинамическая модель океана:
- Доступ через NOAA CoastWatch ERDDAP
- Глобальное покрытие, ежедневные данные

---

## Лицензия

Проект разработан в рамках хакатона **EcoHack** командой **antihype**.
