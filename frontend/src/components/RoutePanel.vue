<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import L from 'leaflet'
import { analyzeRoute } from '../api.js'

const props = defineProps({
  result: Object,
  lat: Number,
  lon: Number,
})

const routeMapEl = ref(null)
let map = null
let layerGroup = null

// Local override of route data (set after manual recalculation)
const localRoute = ref(null)

const route = computed(() => localRoute.value ?? props.result?.route)
const hasRoute = computed(() => route.value && route.value.waypoints?.length > 0)
const firstWP = computed(() => route.value?.waypoints?.[0])

// Recalculate controls
const maxWaypoints = ref(10)
const isRecalculating = ref(false)
const recalcError = ref(null)

async function recalculateRoute() {
  const hotspots = props.result?.hotspots
  if (!hotspots?.length || !props.lat || !props.lon) {
    recalcError.value = 'Нет горячих точек для построения маршрута'
    return
  }
  isRecalculating.value = true
  recalcError.value = null
  try {
    const res = await analyzeRoute({
      raft_lat: props.lat,
      raft_lon: props.lon,
      hotspots,
      max_waypoints: maxWaypoints.value,
    })
    localRoute.value = res
  } catch (err) {
    recalcError.value = err.message || 'Ошибка запроса'
  } finally {
    isRecalculating.value = false
  }
}

onUnmounted(() => {
  if (map) { map.remove(); map = null }
})

onMounted(() => {
  if (!routeMapEl.value) return
  map = L.map(routeMapEl.value, {
    center: [props.lat, props.lon],
    zoom: 7,
    zoomControl: true,
  })

  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { attribution: 'CartoDB', maxZoom: 19 }
  ).addTo(map)

  layerGroup = L.layerGroup().addTo(map)
  renderRoute()
})

watch(() => props.result, renderRoute, { deep: true })

function renderRoute() {
  if (!layerGroup || !map || !hasRoute.value) return
  layerGroup.clearLayers()

  const wps = route.value.waypoints

  // Start marker
  L.marker([props.lat, props.lon], {
    icon: L.divIcon({
      html: '<div style="background:#1565c0;color:#fff;padding:4px 8px;border-radius:4px;font-size:12px;font-weight:bold;white-space:nowrap">START</div>',
      className: '',
      iconSize: null,
    }),
  }).addTo(layerGroup)

  // Route polyline
  const coords = [[props.lat, props.lon], ...wps.map((wp) => [wp.lat, wp.lon])]
  L.polyline(coords, {
    color: '#00e5ff', weight: 3, opacity: 0.9, dashArray: '8 4',
  }).addTo(layerGroup)

  // Waypoint markers
  wps.forEach((wp, i) => {
    const color = wp.fdi_max > 0.01 ? '#ef5350' : '#ff9800'
    L.circleMarker([wp.lat, wp.lon], {
      radius: 8 + Math.min(wp.area_km2 * 2, 10),
      color,
      fillColor: color,
      fillOpacity: 0.8,
      weight: 2,
    }).bindPopup(
      `<b>${wp.label}</b><br>ETA: ${wp.eta_hours.toFixed(1)}ч<br>Курс: ${wp.bearing_deg.toFixed(0)}°<br>Дист: ${wp.distance_km.toFixed(1)} км<br>FDI: ${wp.fdi_max.toFixed(4)}<br>Площадь: ${wp.area_km2.toFixed(3)} км²`
    ).addTo(layerGroup)

    // Label
    L.marker([wp.lat, wp.lon], {
      icon: L.divIcon({
        html: `<div style="background:${color};color:#fff;padding:2px 5px;border-radius:3px;font-size:10px;font-weight:bold">${wp.label}</div>`,
        className: '',
        iconSize: null,
        iconAnchor: [0, -15],
      }),
    }).addTo(layerGroup)
  })

  // Fit bounds
  map.fitBounds(L.latLngBounds(coords).pad(0.2))
}
</script>

<template>
  <div class="panel-content">
    <!-- Recalculate controls — always visible when panel is open -->
    <div class="recalc-bar">
      <label class="recalc-label">Макс. точек маршрута</label>
      <input
        v-model.number="maxWaypoints"
        type="number"
        min="1"
        max="20"
        class="recalc-input"
      />
      <button class="recalc-btn" :disabled="isRecalculating" @click="recalculateRoute">
        <span v-if="isRecalculating" class="spinner"></span>
        <span v-else>Пересчитать маршрут</span>
      </button>
      <span v-if="recalcError" class="recalc-error">{{ recalcError }}</span>
    </div>

    <div v-if="!hasRoute" class="panel-empty">
      <div class="empty-state">
        <p v-if="result?.hotspots?.length">Нажмите «Пересчитать маршрут» или включите «Оптимальный маршрут» в параметрах и нажмите «Анализировать».</p>
        <p v-else>Горячих точек не обнаружено — маршрут строить не к чему.</p>
      </div>
    </div>

    <template v-else>
      <!-- NEXT WAYPOINT hero card -->
      <div class="next-wp-card" v-if="firstWP">
        <div class="next-wp-label">СЛЕДУЮЩАЯ ТОЧКА</div>
        <div class="next-wp-bearing">{{ (firstWP.bearing_deg ?? 0).toFixed(0) }}°</div>
        <div class="next-wp-details">
          {{ (firstWP.distance_km ?? 0).toFixed(1) }} км &middot; ETA {{ (firstWP.eta_hours ?? 0).toFixed(1) }}ч
        </div>
        <div class="next-wp-coords">
          {{ firstWP.lat.toFixed(4) }}°N, {{ firstWP.lon.toFixed(4) }}°E &middot; {{ firstWP.label }}
        </div>
      </div>

      <!-- Route KPI -->
      <div class="drift-kpi">
        <div class="kpi-card">
          <div class="kpi-value accent">{{ route.n_waypoints }}</div>
          <div class="kpi-label">Точек маршрута</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">{{ route.total_distance_km.toFixed(1) }} км</div>
          <div class="kpi-label">Расстояние</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">{{ route.total_eta_hours.toFixed(1) }} ч</div>
          <div class="kpi-label">ETA</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">{{ (route.total_eta_hours / 24).toFixed(1) }}</div>
          <div class="kpi-label">Дней в пути</div>
        </div>
      </div>

      <div class="drift-info">
        Скорость плота: ~2 узла (~3.7 км/ч). Метод: Greedy + 2-opt оптимизация.
      </div>

      <!-- Route map -->
      <div class="drift-map" ref="routeMapEl"></div>

      <!-- Navigation table -->
      <div class="drift-table-section">
        <div class="section-title">Навигационная таблица</div>
        <table class="route-table">
          <thead>
            <tr><th>WP</th><th>Широта</th><th>Долгота</th><th>Курс</th><th>Расст.</th><th>ETA</th><th>FDI</th><th>Площадь</th></tr>
          </thead>
          <tbody>
            <tr v-for="(wp, i) in route.waypoints" :key="i">
              <td>{{ wp.label }}</td>
              <td>{{ wp.lat.toFixed(4) }}°</td>
              <td>{{ wp.lon.toFixed(4) }}°</td>
              <td>{{ (wp.bearing_deg ?? 0).toFixed(0) }}°</td>
              <td>{{ (wp.distance_km ?? 0).toFixed(1) }} км</td>
              <td>{{ (wp.eta_hours ?? 0).toFixed(1) }}ч</td>
              <td>{{ (wp.fdi_max ?? 0).toFixed(4) }}</td>
              <td>{{ (wp.area_km2 ?? 0).toFixed(3) }} км²</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.panel-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 16px;
  gap: 16px;
}

.panel-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.next-wp-card {
  background: var(--bg-secondary);
  border: 2px solid var(--accent);
  border-radius: 12px;
  padding: 24px;
  text-align: center;
}

.next-wp-label {
  font-size: 12px;
  color: var(--text-dim);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.next-wp-bearing {
  font-size: 48px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1.1;
}

.next-wp-details {
  font-size: 18px;
  color: var(--text-bright);
  margin-top: 4px;
}

.next-wp-coords {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 4px;
}

.drift-kpi {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.kpi-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
  min-width: 130px;
  flex: 1;
}

.kpi-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-bright);
}

.kpi-value.accent {
  color: var(--accent);
}

.kpi-label {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

.drift-info {
  font-size: 12px;
  color: var(--text-dim);
}

.drift-map {
  height: 400px;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
}

.drift-table-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.recalc-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
}

.recalc-label {
  font-size: 12px;
  color: var(--text-dim);
  white-space: nowrap;
}

.recalc-input {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-bright);
  padding: 6px 10px;
  font-size: 13px;
  width: 70px;
  text-align: center;
}

.recalc-btn {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: opacity 0.2s;
}

.recalc-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.recalc-error {
  font-size: 12px;
  color: var(--danger, #ef5350);
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
