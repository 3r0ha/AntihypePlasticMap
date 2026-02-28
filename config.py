"""
Global configuration for antihype Plastic Map.

References:
  Biermann et al. (2020) Sci. Rep. 10:5364  doi:10.1038/s41598-020-62298-z
  Kikaki et al. (2020) Remote Sensing 12:2648
"""
import os

S2_BANDS = {
    "B03": "B03",
    "B04": "B04",
    "B06": "B06",
    "B08": "B08",
    "B8A": "B8A",
    "B11": "B11",
    "B12": "B12",
    "SCL": "SCL",
}

WAVELENGTHS = {
    "B03": 560.0, "B04": 665.0, "B06": 740.0,
    "B08": 842.0, "B8A": 865.0, "B11": 1610.0,
}

SCL_CLOUD_VALUES = {0, 1, 3, 8, 9, 10, 11}
SCL_LAND_VALUES = {4, 5}
SCL_WATER_VALUE = 6

PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_COLLECTION = "sentinel-2-l2a"

DEFAULT_BUFFER_DEG = float(os.environ.get("ECOHACK_BUFFER", 0.15))
DEFAULT_DAYS_BACK = int(os.environ.get("ECOHACK_DAYS", 10))
FALLBACK_DAYS_BACK = 90
MAX_CLOUD_COVER = 90

TARGET_RESOLUTION = int(os.environ.get("ECOHACK_RESOLUTION", 200))

# Biermann 2020: 0.02–0.06 for confirmed debris; we use adaptive with floor
FDI_PLASTIC_THRESHOLD = 0.015
FDI_ABSOLUTE_FLOOR = 0.005
NDWI_WATER_THRESHOLD = 0.0
NDVI_MAX_THRESHOLD = 0.2
NDVI_MIN_THRESHOLD = -0.1
NIR_MAX_REFLECTANCE = 0.3
SWIR_MAX_REFLECTANCE = 0.25
PI_PLASTIC_THRESHOLD = 0.48
MIN_CLUSTER_PIXELS = 3

COLORMAP_WATER = "#0a1628"
COLORMAP_LOW = "#ffffb2"
COLORMAP_HIGH = "#d7191c"
OUTPUT_DIR = "outputs"

# Canonical location presets: key -> (lat, lon, name_ru)
PRESETS = {
    "kochi":     (10.0,   76.3,   "Кочи, Индия"),
    "mumbai":    (19.05,  72.85,  "Мумбаи, Индия"),
    "singapore": (1.3,    103.8,  "Сингапурский пролив"),
    "durban":    (-29.85, 31.05,  "Дурбан, ЮАР"),
    "med":       (37.0,   13.0,   "Средиземное море"),
    "black_sea": (42.5,   35.0,   "Чёрное море"),
    "chennai":   (13.1,   80.3,   "Ченнай, Индия"),
    "jakarta":   (-6.1,   106.85, "Джакарта, Индонезия"),
    "osaka":     (35.15,  136.9,  "Осака, Япония"),
}
