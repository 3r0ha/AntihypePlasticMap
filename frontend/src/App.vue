<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue'
import { getPresets, analyze, pollJob, getHealth, downloadBase64 } from './api.js'
import Sidebar from './components/Sidebar.vue'
import MapView from './components/MapView.vue'
import MetricCards from './components/MetricCards.vue'
import StatusBar from './components/StatusBar.vue'
import DriftPanel from './components/DriftPanel.vue'
import RoutePanel from './components/RoutePanel.vue'
import ExportPanel from './components/ExportPanel.vue'
import IndicesPanel from './components/IndicesPanel.vue'
import WelcomeScreen from './components/WelcomeScreen.vue'
import ModeSelector from './components/ModeSelector.vue'
import TemporalPanel from './components/TemporalPanel.vue'

const presets = ref([])
const result = ref(null)
const loading = ref(false)
const error = ref(null)
const warnings = ref([])
const processingTime = ref(null)
const apiOnline = ref(false)
const mapRef = ref(null)
const activeTab = ref('map')
const appMode = ref(null)

const params = reactive({
  lat: 10.0,
  lon: 76.3,
  days_back: 10,
  buffer_deg: 0.5,
  max_cloud_cover: 85,
  include_drift: false,
  include_route: false,
  enable_temporal: false,
  wind_u: 0.0,
  wind_v: 0.0,
})

const tabs = computed(() => {
  const base = [{ id: 'map', label: 'Карта' }]
  if (appMode.value === 'full') {
    base.push({ id: 'indices', label: 'Индексы' })
  }
  base.push({ id: 'drift', label: 'Дрейф' })
  base.push({ id: 'route', label: 'Маршрут' })
  base.push({ id: 'temporal', label: 'Тренды' })
  base.push({ id: 'export', label: 'Экспорт' })
  return base
})

onMounted(async () => {
  try {
    await getHealth()
    apiOnline.value = true
  } catch {
    apiOnline.value = false
  }
  try {
    const data = await getPresets()
    presets.value = data.presets || []
  } catch {}
})

watch(activeTab, async (tab) => {
  if (tab === 'map') {
    await nextTick()
    mapRef.value?.resize?.()
  }
})

function selectPreset(p) {
  params.lat = p.lat
  params.lon = p.lon
  if (mapRef.value?.flyTo) {
    mapRef.value.flyTo(p.lat, p.lon)
  }
}

function chooseMode(mode) {
  appMode.value = mode
}

function resetMode() {
  appMode.value = null
  result.value = null
  error.value = null
  warnings.value = []
  processingTime.value = null
}

function onMapClick({ lat, lon }) {
  params.lat = lat
  params.lon = lon
}

async function runAnalysis() {
  if (loading.value) return
  loading.value = true
  error.value = null
  result.value = null
  warnings.value = []
  processingTime.value = null

  try {
    const job = await analyze({
      lat: params.lat,
      lon: params.lon,
      days_back: params.days_back,
      buffer_deg: params.buffer_deg,
      max_cloud_cover: params.max_cloud_cover,
      include_drift: params.include_drift,
      include_route: params.include_route,
      enable_temporal: params.enable_temporal,
      include_visuals: appMode.value === 'full',
      wind_u: params.wind_u,
      wind_v: params.wind_v,
    })
    const data = await pollJob(job.job_id)
    result.value = data
    warnings.value = data.warnings || []
    processingTime.value = data.processing_time_sec
    apiOnline.value = true
    activeTab.value = 'map'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function flyToHotspot(h) {
  activeTab.value = 'map'
  if (mapRef.value?.flyTo) {
    mapRef.value.flyTo(h.lat, h.lon, 13)
  }
}

function exportJSON() {
  if (!result.value) return
  const { visuals, ...data } = result.value
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `antihype_${params.lat}_${params.lon}.json`
  a.click()
}

function exportGeoJSON() {
  if (!result.value?.hotspots) return
  const geojson = {
    type: 'FeatureCollection',
    features: result.value.hotspots.map((h) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [h.lon, h.lat] },
      properties: { fdi_max: h.fdi_max, area_km2: h.area_km2 },
    })),
  }
  const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/geo+json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `hotspots_${params.lat}_${params.lon}.geojson`
  a.click()
}

function exportRouteGeoJSON() {
  if (!result.value?.route?.waypoints) return
  const coords = result.value.route.waypoints.map((wp) => [wp.lon, wp.lat])
  const geojson = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: coords },
        properties: {
          total_distance_km: result.value.route.total_distance_km,
          total_eta_hours: result.value.route.total_eta_hours,
        },
      },
      ...result.value.route.waypoints.map((wp, i) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [wp.lon, wp.lat] },
        properties: { label: wp.label, order: i + 1, fdi_max: wp.fdi_max, area_km2: wp.area_km2 },
      })),
    ],
  }
  const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/geo+json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `route_${params.lat}_${params.lon}.geojson`
  a.click()
}

function exportPNG() {
  if (!result.value?.visuals?.static_png) return
  downloadBase64(result.value.visuals.static_png, `plastic_map_${params.lat}_${params.lon}.png`, 'image/png')
}

function exportHTML() {
  if (!result.value?.visuals?.folium_html) return
  downloadBase64(result.value.visuals.folium_html, `plastic_map_${params.lat}_${params.lon}.html`, 'text/html')
}

function exportPDF() {
  if (!result.value?.visuals?.pdf) return
  downloadBase64(result.value.visuals.pdf, `antihype_report_${params.lat}_${params.lon}.pdf`, 'application/pdf')
}

const openOceanWarning = computed(() => {
  const { lat, lon } = params
  const isOpen = Math.abs(lat) < 60 && (lon < -30 || lon > 100) && Math.abs(lat) > 10
  const nearLand =
    (Math.abs(lon - 13) < 2 && Math.abs(lat - 37) < 2) ||
    (Math.abs(lon - 25) < 2 && Math.abs(lat - 37.5) < 2) ||
    (Math.abs(lon - 35) < 3 && Math.abs(lat - 42.5) < 3)
  return isOpen && !nearLand
})
</script>

<template>
  <ModeSelector v-if="!appMode" @choose="chooseMode" />

  <template v-else>
    <header class="header">
      <span class="header-logo">antihype</span>
      <span class="header-title">Карта пластика</span>
      <span class="header-mode" @click="resetMode">
        {{ appMode === 'full' ? 'Полная' : 'Лёгкая' }}
      </span>

      <div class="header-tabs" v-if="result">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="header-status">
        <span class="status-dot" :class="{ offline: !apiOnline, loading }"></span>
        <span v-if="loading">Анализ...</span>
        <span v-else-if="apiOnline">API Online</span>
        <span v-else>API Offline</span>
      </div>
    </header>

    <div class="main-layout">
      <Sidebar
        :presets="presets"
        :params="params"
        :loading="loading"
        :result="result"
        :open-ocean-warning="openOceanWarning"
        :mode="appMode"
        @select-preset="selectPreset"
        @analyze="runAnalysis"
        @fly-to="flyToHotspot"
      />

      <div class="map-container" v-show="!result || activeTab === 'map'">
        <MapView
          ref="mapRef"
          :center="[params.lat, params.lon]"
          :result="result"
          :buffer-deg="params.buffer_deg"
          @map-click="onMapClick"
        />
        <WelcomeScreen v-if="!result && !loading" />
        <MetricCards v-if="result && activeTab === 'map'" :stats="result.stats" :hotspots="result.hotspots" />
      </div>

      <IndicesPanel
        v-if="result && activeTab === 'indices' && appMode === 'full'"
        :result="result"
      />

      <DriftPanel
        v-if="result && activeTab === 'drift'"
        :result="result"
        :lat="params.lat"
        :lon="params.lon"
      />

      <RoutePanel
        v-if="result && activeTab === 'route'"
        :result="result"
        :lat="params.lat"
        :lon="params.lon"
      />

      <TemporalPanel
        v-if="result && activeTab === 'temporal'"
        :result="result"
      />

      <ExportPanel
        v-if="result && activeTab === 'export'"
        :result="result"
        :mode="appMode"
        :lat="params.lat"
        :lon="params.lon"
        @export-json="exportJSON"
        @export-geojson="exportGeoJSON"
        @export-route-geojson="exportRouteGeoJSON"
        @export-png="exportPNG"
        @export-html="exportHTML"
        @export-pdf="exportPDF"
      />
    </div>

    <StatusBar
      :loading="loading"
      :error="error"
      :warnings="warnings"
      :processing-time="processingTime"
      :result="result"
    />
  </template>
</template>
