<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import L from 'leaflet'

const props = defineProps({
  center: Array,
  result: Object,
  bufferDeg: { type: Number, default: 0.5 },
})

const emit = defineEmits(['map-click'])

const mapEl = ref(null)
const cursorCoords = ref('')
let map = null
let layerGroup = null
let bufferRect = null

// Fix default marker icons
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

onMounted(() => {
  map = L.map(mapEl.value, {
    center: props.center,
    zoom: 8,
    zoomControl: false,
  })

  L.control.zoom({ position: 'topright' }).addTo(map)

  const esri = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { attribution: 'Esri', maxZoom: 18 }
  )

  const dark = L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { attribution: 'CartoDB', maxZoom: 19 }
  )

  esri.addTo(map)
  L.control.layers({ 'Спутник': esri, 'Тёмная': dark }, {}, { position: 'topright' }).addTo(map)
  L.control.scale({ metric: true, imperial: false, position: 'bottomleft' }).addTo(map)

  layerGroup = L.layerGroup().addTo(map)

  map.on('mousemove', (e) => {
    const lat = e.latlng.lat
    const lon = e.latlng.lng
    const ns = lat >= 0 ? 'N' : 'S'
    const ew = lon >= 0 ? 'E' : 'W'
    cursorCoords.value = `${Math.abs(lat).toFixed(4)}°${ns}, ${Math.abs(lon).toFixed(4)}°${ew}`
  })
  map.on('mouseout', () => { cursorCoords.value = '' })

  map.on('click', (e) => {
    emit('map-click', { lat: parseFloat(e.latlng.lat.toFixed(4)), lon: parseFloat(e.latlng.lng.toFixed(4)) })
  })

  // Legend
  const legend = L.control({ position: 'bottomright' })
  legend.onAdd = () => {
    const div = L.DomUtil.create('div', 'map-legend')
    div.innerHTML = `
      <div style="background:rgba(10,22,40,0.9);padding:8px 10px;border-radius:6px;border:1px solid #1a3a5c;font-size:11px;color:#cdd8e3;line-height:1.6">
        <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#ef5350;margin-right:6px;vertical-align:middle"></span>Хотспоты</div>
        <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#ff9800;margin-right:6px;vertical-align:middle"></span>После дрейфа</div>
        <div><span style="display:inline-block;width:12px;height:3px;background:#00e5ff;margin-right:6px;vertical-align:middle"></span>Маршрут</div>
        <div><span style="display:inline-block;width:12px;height:3px;background:#ff9800;border-top:1px dashed #ff9800;margin-right:6px;vertical-align:middle"></span>Дрейф</div>
      </div>`
    return div
  }
  legend.addTo(map)

  drawBuffer()
})

function flyTo(lat, lon, zoom) {
  if (map) {
    map.invalidateSize()
    map.flyTo([lat, lon], zoom || 10, { duration: 1 })
  }
}

function resize() {
  if (map) map.invalidateSize()
}

function drawBuffer() {
  if (bufferRect) { map.removeLayer(bufferRect); bufferRect = null }
  if (!map || !props.center) return
  const [lat, lon] = props.center
  const b = props.bufferDeg
  bufferRect = L.rectangle(
    [[lat - b, lon - b], [lat + b, lon + b]],
    { color: '#00e5ff', weight: 1, fillOpacity: 0.05, dashArray: '6,4' }
  ).addTo(map)
}

onUnmounted(() => {
  if (map) { map.remove(); map = null }
})

defineExpose({ flyTo, resize })

watch(() => props.center, (c) => {
  if (map && c) { map.setView(c, map.getZoom()); drawBuffer() }
})

watch(() => props.bufferDeg, () => drawBuffer())

watch(() => props.result, async (r) => {
  if (!layerGroup || !map) return

  // Ensure map recalculates after layout changes
  await nextTick()
  map.invalidateSize()
  setTimeout(() => { if (map) map.invalidateSize() }, 200)
  setTimeout(() => { if (map) map.invalidateSize() }, 500)

  layerGroup.clearLayers()
  if (!r) return

  // Hotspots — red circles
  if (r.hotspots) {
    r.hotspots.forEach((h) => {
      const radius = Math.max(500, Math.sqrt((h.area_km2 || 0.01) * 1e6))
      L.circle([h.lat, h.lon], {
        radius,
        color: '#ef5350',
        fillColor: '#ef5350',
        fillOpacity: 0.3,
        weight: 2,
      })
        .bindPopup(
          `<b>Хотспот</b><br>FDI: ${h.fdi_max.toFixed(4)}<br>Площадь: ${(h.area_km2 || 0).toFixed(2)} км²<br>${h.lat.toFixed(4)}, ${h.lon.toFixed(4)}`
        )
        .addTo(layerGroup)
    })
  }

  // Drift-corrected — orange circles
  if (r.hotspots_drift_corrected) {
    r.hotspots_drift_corrected.forEach((h) => {
      if (h.lat == null || h.lon == null) return
      const radius = Math.max(500, Math.sqrt((h.area_km2 || 0.01) * 1e6))
      L.circle([h.lat, h.lon], {
        radius,
        color: '#ff9800',
        fillColor: '#ff9800',
        fillOpacity: 0.25,
        weight: 2,
        dashArray: '5,5',
      })
        .bindPopup(
          `<b>После дрейфа</b><br>FDI: ${(h.fdi_max || 0).toFixed(4)}<br>${h.lat.toFixed(4)}, ${h.lon.toFixed(4)}`
        )
        .addTo(layerGroup)
    })
  }

  // Drift trajectories
  if (r.drift) {
    r.drift.forEach((d) => {
      if (d.origin && d.position_48h) {
        const points = [
          [d.origin.lat, d.origin.lon],
        ]
        if (d.position_24h) points.push([d.position_24h.lat, d.position_24h.lon])
        if (d.position_48h) points.push([d.position_48h.lat, d.position_48h.lon])

        L.polyline(points, {
          color: '#ff9800',
          weight: 2,
          opacity: 0.7,
          dashArray: '8,4',
        }).addTo(layerGroup)

        if (d.position_24h) {
          L.circle([d.position_24h.lat, d.position_24h.lon], {
            radius: d.distance_km_24h * 100,
            color: '#ff9800',
            fillOpacity: 0.05,
            weight: 1,
          }).addTo(layerGroup)
        }

        if (d.position_48h) {
          L.circle([d.position_48h.lat, d.position_48h.lon], {
            radius: d.distance_km_48h * 100,
            color: '#ff9800',
            fillOpacity: 0.03,
            weight: 1,
          }).addTo(layerGroup)
        }
      }
    })
  }

  // Route — cyan polyline
  if (r.route?.waypoints) {
    const routePoints = r.route.waypoints.map((wp) => [wp.lat, wp.lon])
    if (routePoints.length > 1) {
      L.polyline(routePoints, {
        color: '#00e5ff',
        weight: 3,
        opacity: 0.8,
      }).addTo(layerGroup)
    }

    r.route.waypoints.forEach((wp, i) => {
      L.circleMarker([wp.lat, wp.lon], {
        radius: i === 0 ? 8 : 6,
        color: '#00e5ff',
        fillColor: i === 0 ? '#00e5ff' : '#0a1628',
        fillOpacity: 1,
        weight: 2,
      })
        .bindPopup(
          `<b>WP ${i + 1}: ${wp.label || ''}</b><br>Курс: ${wp.bearing_deg.toFixed(0)}°<br>Дист: ${wp.distance_km.toFixed(1)} км<br>ETA: ${wp.eta_hours.toFixed(1)}ч`
        )
        .addTo(layerGroup)
    })
  }

  // Fit bounds to hotspots
  if (r.hotspots?.length) {
    const bounds = L.latLngBounds(r.hotspots.map((h) => [h.lat, h.lon]))
    if (r.hotspots_drift_corrected) {
      r.hotspots_drift_corrected.forEach((h) => {
        if (h.lat && h.lon) bounds.extend([h.lat, h.lon])
      })
    }
    map.fitBounds(bounds.pad(0.3), { maxZoom: 12 })
  }
}, { deep: true })
</script>

<template>
  <div style="height: 100%; width: 100%; position: relative">
    <div ref="mapEl" style="height: 100%; width: 100%"></div>
    <div v-if="cursorCoords" class="cursor-coords">{{ cursorCoords }}</div>
  </div>
</template>

<style scoped>
.cursor-coords {
  position: absolute;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(10, 22, 40, 0.85);
  color: #90caf9;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  z-index: 800;
  pointer-events: none;
  border: 1px solid rgba(0, 229, 255, 0.2);
}
</style>
