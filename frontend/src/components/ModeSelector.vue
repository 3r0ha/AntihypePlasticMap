<script setup>
const emit = defineEmits(['choose'])
</script>

<template>
  <div class="mode-screen">
    <div class="mode-content">
      <h1 class="mode-title">antihype · Карта пластика</h1>
      <p class="mode-subtitle">Выберите режим работы</p>

      <div class="mode-cards">
        <div class="mode-card" @click="emit('choose', 'lite')">
          <div class="mode-card-icon">&#9889;</div>
          <div class="mode-card-name">Лёгкая версия</div>
          <div class="mode-card-desc">
            Минимум загрузок. Только карта, хотспоты, дрейф и маршрут.
            Оптимально для спутникового интернета и медленного соединения.
          </div>
          <ul class="mode-features">
            <li>Интерактивная карта Leaflet</li>
            <li>Хотспоты + дрейф + маршрут</li>
            <li>Метрики и статистика</li>
            <li>Экспорт JSON / GeoJSON</li>
          </ul>
          <div class="mode-badge lite">~50 KB трафика</div>
        </div>

        <div class="mode-card" @click="emit('choose', 'full')">
          <div class="mode-card-icon">&#128640;</div>
          <div class="mode-card-name">Полная версия</div>
          <div class="mode-card-desc">
            Все визуализации: спектральные индексы, гистограммы, карта уверенности,
            интерактивная Folium карта, PDF отчёт.
          </div>
          <ul class="mode-features">
            <li>Всё из лёгкой версии</li>
            <li>6 графиков спектральных индексов</li>
            <li>Карта уверенности детекции</li>
            <li>Folium HTML карта + PNG + PDF отчёт</li>
          </ul>
          <div class="mode-badge full">~2-5 MB трафика</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mode-screen {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  padding: 40px;
}

.mode-content {
  text-align: center;
  max-width: 800px;
}

.mode-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 8px;
}

.mode-subtitle {
  color: var(--text-dim);
  font-size: 16px;
  margin-bottom: 40px;
}

.mode-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.mode-card {
  background: var(--bg-secondary);
  border: 2px solid var(--border);
  border-radius: 12px;
  padding: 32px 24px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.mode-card:hover {
  border-color: var(--accent);
  transform: translateY(-4px);
  box-shadow: 0 8px 32px rgba(0, 229, 255, 0.15);
}

.mode-card-icon {
  font-size: 36px;
  margin-bottom: 12px;
}

.mode-card-name {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-bright);
  margin-bottom: 8px;
}

.mode-card-desc {
  font-size: 13px;
  color: var(--text-dim);
  line-height: 1.5;
  margin-bottom: 16px;
}

.mode-features {
  list-style: none;
  padding: 0;
  margin-bottom: 16px;
}

.mode-features li {
  font-size: 13px;
  color: var(--text);
  padding: 3px 0;
}

.mode-features li::before {
  content: '\2713';
  color: var(--accent);
  margin-right: 8px;
  font-weight: bold;
}

.mode-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.mode-badge.lite {
  background: rgba(102, 187, 106, 0.15);
  color: var(--success);
}

.mode-badge.full {
  background: rgba(0, 229, 255, 0.15);
  color: var(--accent);
}
</style>
