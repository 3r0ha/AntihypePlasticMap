<script setup>
defineProps({
  loading: Boolean,
  error: String,
  warnings: Array,
  processingTime: Number,
  result: Object,
})
</script>

<template>
  <footer class="footer">
    <span v-if="loading">Выполняется анализ спутниковых данных...</span>
    <span v-else-if="error" class="footer-warning">{{ error }}</span>
    <template v-else-if="result">
      <span>Снимков: {{ result.scenes_found || 0 }}</span>
      <span v-if="result.scene_dates?.length">Даты: {{ result.scene_dates.join(', ') }}</span>
      <span v-if="processingTime">Время: {{ processingTime.toFixed(1) }}с</span>
    </template>
    <span v-else>Выберите локацию и нажмите «Анализировать»</span>
    <span v-if="warnings?.length" class="footer-warning" :title="warnings.join('\n')">{{ warnings.length }} предупр.: {{ warnings[0] }}{{ warnings.length > 1 ? ` (+${warnings.length - 1})` : '' }}</span>
  </footer>
</template>
