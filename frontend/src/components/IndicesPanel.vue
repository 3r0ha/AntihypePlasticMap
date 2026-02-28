<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: Object,
})

const indicesPng = computed(() => props.result?.visuals?.indices_png)

const stats = computed(() => props.result?.stats || {})
</script>

<template>
  <div class="panel-content">
    <div class="panel-header">
      <h2>Сравнение спектральных индексов</h2>
      <p class="panel-desc">
        Каждый индекс по-своему чувствителен к плавающему мусору.
        Сравнение помогает отличить пластик от водорослей (Саргассум) и пены.
      </p>
    </div>

    <div class="indices-info">
      <div class="info-col">
        <table class="route-table">
          <thead>
            <tr><th>Индекс</th><th>Чувствителен к</th><th>Фильтрует</th></tr>
          </thead>
          <tbody>
            <tr><td><b>FDI</b></td><td>Пластик, пена</td><td>Чистая вода</td></tr>
            <tr><td><b>FAI</b></td><td>Водоросли + пластик</td><td>—</td></tr>
            <tr><td><b>PI</b></td><td>Пластик (NIR/Red)</td><td>Вода, земля</td></tr>
            <tr><td><b>NDVI</b></td><td>Водоросли</td><td>Пластик, вода</td></tr>
          </tbody>
        </table>
      </div>
      <div class="info-col">
        <div class="detection-logic">
          <div class="section-title">Логика детекции пластика</div>
          <ol>
            <li>FDI &gt; порог &rarr; плавающий материал</li>
            <li>NDWI &gt; 0 &rarr; водный пиксель</li>
            <li>NDVI &lt; 0.15 &rarr; не водоросли</li>
          </ol>
          <p>Только пиксели, прошедшие <b>все 3 условия</b> = пластик.</p>
        </div>
      </div>
    </div>

    <div v-if="indicesPng" class="visual-section">
      <img :src="'data:image/png;base64,' + indicesPng" alt="Спектральные индексы" class="visual-img" />
    </div>
    <div v-else class="empty-state">
      Визуализация индексов недоступна. Убедитесь, что выбран полный режим.
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
  margin-bottom: 4px;
}

.panel-desc {
  font-size: 13px;
  color: var(--text-dim);
}

.indices-info {
  display: flex;
  gap: 16px;
}

.info-col {
  flex: 1;
}

.detection-logic {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.detection-logic ol {
  padding-left: 20px;
  margin: 8px 0;
}

.detection-logic li {
  font-size: 13px;
  color: var(--text);
  padding: 2px 0;
}

.detection-logic p {
  font-size: 13px;
  color: var(--text-dim);
  margin-top: 8px;
}

.visual-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
}

.visual-img {
  width: 100%;
  height: auto;
  border-radius: 4px;
}
</style>
