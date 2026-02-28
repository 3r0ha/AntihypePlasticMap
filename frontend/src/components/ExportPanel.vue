<script setup>
const props = defineProps({
  result: Object,
  mode: String,
  lat: Number,
  lon: Number,
})

const emit = defineEmits([
  'export-json', 'export-geojson', 'export-route-geojson',
  'export-png', 'export-html', 'export-pdf',
])

import { computed } from 'vue'

const hasVisuals = computed(() => props.result?.visuals)
const hasRoute = computed(() => props.result?.route)
const hasHotspots = computed(() => props.result?.hotspots?.length)
</script>

<template>
  <div class="panel-content">
    <div class="panel-header">
      <h2>Экспорт данных</h2>
    </div>

    <div class="export-grid">
      <!-- Map exports -->
      <div class="export-section">
        <div class="section-title">Карта</div>
        <div class="export-btns-col">
          <button class="btn-export-lg" v-if="hasVisuals && hasVisuals.folium_html" @click="emit('export-html')">
            <span class="btn-icon">&#127758;</span>
            <span>
              <b>HTML (интерактивная)</b>
              <small>Folium карта с FDI overlay, хотспотами, дрейфом</small>
            </span>
          </button>
          <button class="btn-export-lg" v-if="hasVisuals && hasVisuals.static_png" @click="emit('export-png')">
            <span class="btn-icon">&#128444;</span>
            <span>
              <b>PNG (статичная)</b>
              <small>4-панельный обзор: RGB, FDI, маска, уверенность</small>
            </span>
          </button>
        </div>
      </div>

      <!-- Data exports -->
      <div class="export-section">
        <div class="section-title">Данные</div>
        <div class="export-btns-col">
          <button class="btn-export-lg" v-if="hasHotspots" @click="emit('export-geojson')">
            <span class="btn-icon">&#128205;</span>
            <span>
              <b>GeoJSON (горячие точки)</b>
              <small>{{ result.hotspots.length }} точек с FDI и площадью</small>
            </span>
          </button>
          <button class="btn-export-lg" v-if="hasRoute" @click="emit('export-route-geojson')">
            <span class="btn-icon">&#129517;</span>
            <span>
              <b>GeoJSON (маршрут)</b>
              <small>{{ result.route.n_waypoints }} waypoints, {{ result.route.total_distance_km.toFixed(1) }} км</small>
            </span>
          </button>
          <button class="btn-export-lg" @click="emit('export-json')">
            <span class="btn-icon">&#128202;</span>
            <span>
              <b>JSON (статистика)</b>
              <small>Полные данные анализа без визуализаций</small>
            </span>
          </button>
        </div>
      </div>

      <!-- Report -->
      <div class="export-section">
        <div class="section-title">Отчёт</div>
        <div class="export-btns-col">
          <button class="btn-export-lg" v-if="hasVisuals && hasVisuals.pdf" @click="emit('export-pdf')">
            <span class="btn-icon">&#128196;</span>
            <span>
              <b>PDF миссионный отчёт</b>
              <small>Параметры, статистика, карты, хотспоты, маршрут</small>
            </span>
          </button>
          <div v-else-if="mode === 'lite'" class="export-note">
            PDF отчёт доступен в полной версии.
          </div>
        </div>
      </div>
    </div>

    <!-- Report contents info -->
    <div class="report-info" v-if="mode === 'full'">
      <div class="section-title">Содержание PDF отчёта</div>
      <ul>
        <li>Параметры миссии</li>
        <li>Таблица статистики</li>
        <li>Карта FDI + детекции пластика</li>
        <li>Список горячих точек с координатами</li>
        <li>Прогноз дрейфа (если включён)</li>
        <li>Навигационная таблица маршрута</li>
        <li>Методологический раздел</li>
      </ul>
    </div>
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

.panel-header h2 {
  font-size: 18px;
  color: var(--accent);
}

.export-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.export-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.export-btns-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.btn-export-lg {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 12px;
  border-radius: var(--radius);
  cursor: pointer;
  font-family: var(--font);
  text-align: left;
  transition: all 0.15s;
  width: 100%;
}

.btn-export-lg:hover {
  border-color: var(--accent);
  background: var(--accent-dim);
}

.btn-icon {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}

.btn-export-lg b {
  display: block;
  font-size: 13px;
  color: var(--text-bright);
  margin-bottom: 2px;
}

.btn-export-lg small {
  display: block;
  font-size: 11px;
  color: var(--text-dim);
}

.export-note {
  font-size: 12px;
  color: var(--text-dim);
  padding: 8px;
}

.report-info {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.report-info ul {
  list-style: none;
  padding: 0;
  margin-top: 8px;
}

.report-info li {
  font-size: 13px;
  color: var(--text);
  padding: 3px 0;
}

.report-info li::before {
  content: '\2713';
  color: var(--accent);
  margin-right: 8px;
}
</style>
