<script setup>
import { computed } from 'vue'

const props = defineProps({
  presets: Array,
  params: Object,
  loading: Boolean,
  result: Object,
  openOceanWarning: Boolean,
  mode: String,
})

const emit = defineEmits(['select-preset', 'analyze', 'fly-to', 'export-json'])

const hotspots = computed(() => props.result?.hotspots || [])
const driftHotspots = computed(() => props.result?.hotspots_drift_corrected || [])
const route = computed(() => props.result?.route)
</script>

<template>
  <aside class="sidebar">
    <!-- Presets -->
    <div class="sidebar-section">
      <div class="section-title">Локации</div>
      <div class="preset-grid">
        <button
          v-for="p in presets"
          :key="p.id"
          class="preset-btn"
          :class="{ active: params.lat === p.lat && params.lon === p.lon }"
          @click="emit('select-preset', p)"
        >
          {{ p.name }}
        </button>
      </div>
    </div>

    <!-- Coordinates -->
    <div class="sidebar-section">
      <div class="section-title">Координаты</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Широта N</label>
          <input class="form-input" type="number" v-model.number="params.lat" step="0.1" min="-90" max="90" />
        </div>
        <div class="form-group">
          <label class="form-label">Долгота E</label>
          <input class="form-input" type="number" v-model.number="params.lon" step="0.1" min="-180" max="180" />
        </div>
      </div>
      <div v-if="openOceanWarning" class="warning-box">
        Открытый океан — Sentinel-2 снимает в основном сушу. Снимки редкие. Попробуйте Средиземное/Чёрное море.
      </div>
    </div>

    <!-- Parameters -->
    <div class="sidebar-section">
      <div class="section-title">Параметры</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Период (дней)</label>
          <input class="form-input" type="number" v-model.number="params.days_back" min="1" max="30" />
        </div>
        <div class="form-group">
          <label class="form-label">Облачность %</label>
          <input class="form-input" type="number" v-model.number="params.max_cloud_cover" min="10" max="100" step="5" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Радиус (°)</label>
          <input class="form-input" type="number" v-model.number="params.buffer_deg" step="0.1" min="0.1" max="3" />
        </div>
      </div>
    </div>

    <!-- Options -->
    <div class="sidebar-section">
      <div class="section-title">Дополнительно</div>
      <label class="checkbox-row">
        <input type="checkbox" v-model="params.include_drift" />
        <span>Прогноз дрейфа (48ч)</span>
      </label>
      <label class="checkbox-row">
        <input type="checkbox" v-model="params.include_route" />
        <span>Оптимальный маршрут</span>
      </label>
      <label class="checkbox-row">
        <input type="checkbox" v-model="params.enable_temporal" />
        <span>Темпоральная аномалия</span>
      </label>
    </div>

    <!-- Wind -->
    <div class="sidebar-section">
      <div class="section-title">Ветер (наблюдаемый)</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label" title="Восточная составляющая ветра">U (м/с)</label>
          <input class="form-input" type="number" v-model.number="params.wind_u" step="0.5" min="-20" max="20" title="Восточная составляющая ветра (положительная = на восток)" />
        </div>
        <div class="form-group">
          <label class="form-label" title="Северная составляющая ветра">V (м/с)</label>
          <input class="form-input" type="number" v-model.number="params.wind_v" step="0.5" min="-20" max="20" title="Северная составляющая ветра (положительная = на север)" />
        </div>
      </div>
    </div>

    <!-- Analyze button -->
    <div class="sidebar-section">
      <button class="btn-analyze" :disabled="loading" @click="emit('analyze')">
        <template v-if="loading">Анализ...</template>
        <template v-else>Анализировать</template>
      </button>
      <div v-if="loading" class="progress-bar"><div class="progress-fill"></div></div>
    </div>

    <!-- Hotspots -->
    <div class="sidebar-section" v-if="hotspots.length">
      <div class="section-title">Хотспоты ({{ hotspots.length }})</div>
      <div
        v-for="(h, i) in hotspots.slice(0, 10)"
        :key="'h' + i"
        class="hotspot-item"
        tabindex="0"
        role="button"
        @click="emit('fly-to', h)"
        @keydown.enter="emit('fly-to', h)"
      >
        <span class="hotspot-dot"></span>
        <span class="hotspot-info">{{ h.lat.toFixed(3) }}, {{ h.lon.toFixed(3) }}</span>
        <span class="hotspot-fdi">{{ h.fdi_max.toFixed(4) }}</span>
      </div>
    </div>

    <!-- Drift-corrected -->
    <div class="sidebar-section" v-if="driftHotspots && driftHotspots.length">
      <div class="section-title">После дрейфа ({{ driftHotspots.length }})</div>
      <div
        v-for="(h, i) in driftHotspots.slice(0, 8)"
        :key="'d' + i"
        class="hotspot-item"
        @click="emit('fly-to', h)"
      >
        <span class="hotspot-dot drift"></span>
        <span class="hotspot-info">{{ h.lat.toFixed(3) }}, {{ h.lon.toFixed(3) }}</span>
        <span class="hotspot-fdi" v-if="h.fdi_max">{{ h.fdi_max.toFixed(4) }}</span>
      </div>
    </div>

    <!-- Quick route summary -->
    <div class="sidebar-section" v-if="route">
      <div class="section-title">
        Маршрут — {{ route.total_distance_km.toFixed(1) }} км
      </div>
      <div class="route-summary">
        {{ route.n_waypoints }} точек, ETA {{ route.total_eta_hours.toFixed(1) }}ч
      </div>
    </div>
  </aside>
</template>
