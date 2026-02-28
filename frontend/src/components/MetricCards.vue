<script setup>
import { computed } from 'vue'

const props = defineProps({
  stats: Object,
  hotspots: Array,
})

const cards = computed(() => {
  const s = props.stats || {}
  return [
    {
      label: 'Площадь пластика',
      value: `${(s.plastic_area_km2 || 0).toFixed(2)} км²`,
      cls: s.plastic_area_km2 > 0 ? 'danger' : 'success',
    },
    {
      label: 'Покрытие',
      value: `${(s.plastic_coverage_pct || 0).toFixed(2)}%`,
      cls: s.plastic_coverage_pct > 1 ? 'danger' : s.plastic_coverage_pct > 0 ? 'warning' : 'success',
    },
    {
      label: 'FDI макс.',
      value: (s.fdi_max || 0).toFixed(4),
      cls: 'accent',
    },
    {
      label: 'Уверенность',
      value: `${((s.confidence_mean || 0) * 100).toFixed(0)}%`,
      cls: s.confidence_mean > 0.5 ? 'success' : 'warning',
    },
    {
      label: 'Хотспоты',
      value: (props.hotspots || []).length,
      cls: (props.hotspots || []).length > 0 ? 'danger' : 'success',
    },
    {
      label: 'Облачность',
      value: `${(s.cloud_coverage_pct || 0).toFixed(1)}%`,
      cls: s.cloud_coverage_pct > 50 ? 'warning' : 'accent',
    },
    {
      label: 'Порог FDI',
      value: s.fdi_threshold_used != null ? s.fdi_threshold_used.toFixed(4) : '—',
      cls: 'accent',
    },
    {
      label: 'Glint пикс.',
      value: s.glint_pixels ?? '—',
      cls: s.glint_pixels > 100 ? 'warning' : 'accent',
    },
  ]
})
</script>

<template>
  <div class="metric-cards">
    <div v-for="(c, i) in cards" :key="i" class="metric-card">
      <div class="metric-value" :class="c.cls">{{ c.value }}</div>
      <div class="metric-label">{{ c.label }}</div>
    </div>
  </div>
</template>
