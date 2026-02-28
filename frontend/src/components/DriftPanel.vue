<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import L from 'leaflet'
import { analyzeDrift } from '../api.js'

const props = defineProps({
  result: Object,
  lat: Number,
  lon: Number,
})

const driftMapEl = ref(null)
let map = null
let layerGroup = null

// Local override of drift data (set after manual recalculation)
const localDrift = ref(null)

const drift = computed(() => localDrift.value ?? props.result?.drift ?? [])
const hasDrift = computed(() => drift.value.length > 0)
const topDrift = computed(() => drift.value[0] || null)

// Recalculate controls
const selectedHours = ref(72)
const isRecalculating = ref(false)
const recalcError = ref(null)

async function recalculateDrift() {
  if (!props.lat || !props.lon) return
  isRecalculating.value = true
  recalcError.value = null
  try {
    const res = await analyzeDrift({
      lat: props.lat,
      lon: props.lon,
      hours: selectedHours.value,
    })
    // Wrap single drift result into the same list shape the panel expects
    localDrift.value = [
      {
        hotspot: { lat: props.lat, lon: props.lon },
        origin: res.origin,
        position_24h: res.position_24h,
        position_48h: res.position_48h,
        distance_km_24h: res.distance_km_24h,
        distance_km_48h: res.distance_km_48h,
        current_speed_ms: res.current_speed_ms,
        current_direction_deg: res.current_direction_deg,
        current_source: res.current_source,
        is_synthetic: res.is_synthetic,
      },
    ]
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
  if (!driftMapEl.value) return
  map = L.map(driftMapEl.value, {
    center: [props.lat, props.lon],
    zoom: 7,
    zoomControl: true,
  })

  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { attribution: 'Esri', maxZoom: 18 }
  ).addTo(map)

  layerGroup = L.layerGroup().addTo(map)
  renderDrift()
})

watch(() => props.result, renderDrift, { deep: true })

function renderDrift() {
  if (!layerGroup || !map) return
  layerGroup.clearLayers()
  if (!hasDrift.value) return

  drift.value.forEach((d) => {
    if (!d.origin || !d.position_48h) return

    // Origin marker
    L.circleMarker([d.origin.lat, d.origin.lon], {
      radius: 8, color: '#ef5350', fillColor: '#ef5350', fillOpacity: 0.9, weight: 2,
    }).bindPopup(`<b>Начало</b><br>${d.origin.lat.toFixed(4)}N, ${d.origin.lon.toFixed(4)}E`).addTo(layerGroup)

    // Trajectory line
    const points = [[d.origin.lat, d.origin.lon]]
    if (d.position_24h) points.push([d.position_24h.lat, d.position_24h.lon])
    if (d.position_48h) points.push([d.position_48h.lat, d.position_48h.lon])
    L.polyline(points, { color: '#ff7043', weight: 2.5, opacity: 0.8, dashArray: '8,4' }).addTo(layerGroup)

    // 24h marker
    if (d.position_24h) {
      L.marker([d.position_24h.lat, d.position_24h.lon], {
        icon: L.divIcon({
          html: '<div style="background:#ff9800;color:#fff;padding:3px 6px;border-radius:4px;font-size:11px;font-weight:bold;white-space:nowrap;box-shadow:1px 1px 3px rgba(0,0,0,0.5)">24ч</div>',
          className: '',
          iconSize: null,
        }),
      }).addTo(layerGroup)

      L.circle([d.position_24h.lat, d.position_24h.lon], {
        radius: d.distance_km_24h * 100, color: '#ff9800', fillOpacity: 0.05, weight: 1,
      }).addTo(layerGroup)
    }

    // 48h marker
    if (d.position_48h) {
      L.marker([d.position_48h.lat, d.position_48h.lon], {
        icon: L.divIcon({
          html: '<div style="background:#f44336;color:#fff;padding:3px 6px;border-radius:4px;font-size:11px;font-weight:bold;white-space:nowrap;box-shadow:1px 1px 3px rgba(0,0,0,0.5)">48ч</div>',
          className: '',
          iconSize: null,
        }),
      }).addTo(layerGroup)

      L.circle([d.position_48h.lat, d.position_48h.lon], {
        radius: d.distance_km_48h * 100, color: '#f44336', fillOpacity: 0.03, weight: 1,
      }).addTo(layerGroup)
    }
  })

  // Fit bounds
  const allPoints = []
  drift.value.forEach((d) => {
    if (d.origin) allPoints.push([d.origin.lat, d.origin.lon])
    if (d.position_24h) allPoints.push([d.position_24h.lat, d.position_24h.lon])
    if (d.position_48h) allPoints.push([d.position_48h.lat, d.position_48h.lon])
  })
  if (allPoints.length > 1) {
    map.fitBounds(L.latLngBounds(allPoints).pad(0.3))
  }
}
</script>

<template>
  <div class="panel-content">
    <!-- Recalculate controls — always visible when panel is open -->
    <div class="recalc-bar">
      <label class="recalc-label">Горизонт прогноза</label>
      <select v-model="selectedHours" class="recalc-select">
        <option :value="24">24 ч</option>
        <option :value="48">48 ч</option>
        <option :value="72">72 ч</option>
        <option :value="96">96 ч</option>
        <option :value="168">168 ч (7 дней)</option>
      </select>
      <button class="recalc-btn" :disabled="isRecalculating" @click="recalculateDrift">
        <span v-if="isRecalculating" class="spinner"></span>
        <span v-else>Пересчитать дрейф</span>
      </button>
      <span v-if="recalcError" class="recalc-error">{{ recalcError }}</span>
    </div>

    <div v-if="!hasDrift" class="panel-empty">
      <div class="empty-state">
        <p v-if="result?.hotspots?.length">Включите «Прогноз дрейфа» в параметрах и нажмите «Анализировать».</p>
        <p v-else>Горячих точек не обнаружено — нажмите «Пересчитать дрейф» для анализа текущей позиции.</p>
      </div>
    </div>

    <template v-else>
      <!-- KPI Cards -->
      <div class="drift-kpi">
        <div class="kpi-card">
          <div class="kpi-value">{{ (topDrift.distance_km_24h ?? 0).toFixed(1) }} км</div>
          <div class="kpi-label">Смещение 24ч</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">{{ (topDrift.distance_km_48h ?? 0).toFixed(1) }} км</div>
          <div class="kpi-label">Смещение 48ч</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">{{ (topDrift.current_speed_ms ?? 0).toFixed(2) }} м/с</div>
          <div class="kpi-label">Скорость течения</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">{{ (topDrift.current_direction_deg ?? 0).toFixed(0) }}°</div>
          <div class="kpi-label">Направление</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-value">{{ topDrift.current_source }}</div>
          <div class="kpi-label">Источник</div>
        </div>
        <div class="kpi-card" v-if="topDrift.is_synthetic">
          <div class="kpi-value warning">Синтет.</div>
          <div class="kpi-label">Тип данных</div>
        </div>
      </div>

      <div class="drift-info" v-if="!topDrift.is_synthetic">
        Ансамбль: 30 частиц &middot; Физика: течение + стоксов дрейф + парусность пластика 2.5%
      </div>
      <div class="drift-info warning-text" v-else>
        Синтетическая модель (Open-Meteo недоступен).
      </div>

      <!-- Drift map -->
      <div class="drift-map" ref="driftMapEl"></div>

      <!-- Positions table -->
      <div class="drift-table-section">
        <div class="section-title">Прогнозные позиции</div>
        <table class="route-table">
          <thead>
            <tr><th>Хотспот</th><th>24ч</th><th>48ч</th><th>Смещ. 24ч</th><th>Смещ. 48ч</th></tr>
          </thead>
          <tbody>
            <tr v-for="(d, i) in drift" :key="i">
              <td>{{ d.hotspot.lat.toFixed(4) }}, {{ d.hotspot.lon.toFixed(4) }}</td>
              <td v-if="d.position_24h">{{ d.position_24h.lat.toFixed(4) }}, {{ d.position_24h.lon.toFixed(4) }}</td>
              <td v-else>—</td>
              <td v-if="d.position_48h">{{ d.position_48h.lat.toFixed(4) }}, {{ d.position_48h.lon.toFixed(4) }}</td>
              <td v-else>—</td>
              <td>{{ (d.distance_km_24h ?? 0).toFixed(1) }} км</td>
              <td>{{ (d.distance_km_48h ?? 0).toFixed(1) }} км</td>
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

.kpi-value.warning {
  color: var(--warning);
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

.warning-text {
  color: var(--warning);
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

.recalc-select {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-bright);
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
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
