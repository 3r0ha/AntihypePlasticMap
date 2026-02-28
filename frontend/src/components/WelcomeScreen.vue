<script setup>
</script>

<template>
  <div class="welcome-screen">
    <div class="welcome-content">
      <h1 class="welcome-title">antihype · Карта пластика</h1>
      <p class="welcome-subtitle">
        Детекция скоплений морского пластика &middot; Sentinel-2 FDI &middot;
        Microsoft Planetary Computer &middot; Экспедиция Фёдора Конюхова
      </p>

      <div class="welcome-cards">
        <div class="welcome-card">
          <div class="welcome-card-title">Данные</div>
          <ul>
            <li>Sentinel-2 L2A</li>
            <li>100м разрешение (настраиваемо)</li>
            <li>Microsoft Planetary Computer</li>
            <li>Обновление каждые 5 дней</li>
          </ul>
        </div>
        <div class="welcome-card">
          <div class="welcome-card-title">Алгоритм</div>
          <ul>
            <li>FDI (Biermann 2020)</li>
            <li>FAI, PI, NDVI индексы</li>
            <li>SCL маска облаков</li>
            <li>Медианный композит</li>
          </ul>
        </div>
        <div class="welcome-card">
          <div class="welcome-card-title">Возможности</div>
          <ul>
            <li>Прогноз дрейфа 72ч</li>
            <li>Оптимальный маршрут</li>
            <li>GeoJSON / JSON экспорт</li>
            <li>REST API</li>
          </ul>
        </div>
      </div>

      <div class="welcome-formula">
        <div class="welcome-card-title">Формула FDI — Floating Debris Index</div>
        <div class="formula-text">
          FDI = B<sub>8A</sub> - [ B<sub>6</sub> + (B<sub>11</sub> - B<sub>6</sub>) &times;
          (&lambda;<sub>8A</sub> - &lambda;<sub>6</sub>) / (&lambda;<sub>11</sub> - &lambda;<sub>6</sub>) ]
        </div>
        <table class="formula-table">
          <thead>
            <tr><th>Канал</th><th>&lambda;, нм</th><th>Роль</th></tr>
          </thead>
          <tbody>
            <tr><td>B6</td><td>740</td><td>Red Edge 2 — базовая линия</td></tr>
            <tr><td>B8A</td><td>865</td><td>NIR narrow — целевой канал</td></tr>
            <tr><td>B11</td><td>1610</td><td>SWIR 1 — базовая линия</td></tr>
          </tbody>
        </table>
        <p class="formula-note">
          Пластик имеет повышенное отражение в NIR относительно чистой воды,
          создавая положительную аномалию FDI. Биологический мусор (Саргассум) фильтруется через NDVI.
          <br />
          <em>Biermann et al. (2020) Scientific Reports 10:5364</em>
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.welcome-screen {
  position: absolute;
  inset: 0;
  z-index: 900;
  background: var(--bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  overflow-y: auto;
}

.welcome-content {
  max-width: 800px;
}

.welcome-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 8px;
}

.welcome-subtitle {
  color: var(--text-dim);
  font-size: 14px;
  margin-bottom: 32px;
}

.welcome-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.welcome-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.welcome-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 10px;
}

.welcome-card ul {
  list-style: none;
  padding: 0;
}

.welcome-card li {
  font-size: 13px;
  color: var(--text);
  padding: 3px 0;
}

.welcome-card li::before {
  content: '•';
  color: var(--accent);
  margin-right: 8px;
}

.welcome-formula {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}

.formula-text {
  font-size: 18px;
  font-family: 'Cambria Math', 'Georgia', serif;
  color: var(--text-bright);
  text-align: center;
  padding: 16px 0;
  background: var(--bg-primary);
  border-radius: 4px;
  margin-bottom: 16px;
}

.formula-table {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
  margin-bottom: 12px;
}

.formula-table th {
  text-align: left;
  padding: 6px 10px;
  background: rgba(0, 229, 255, 0.1);
  color: var(--accent);
  font-weight: 500;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.formula-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}

.formula-note {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
}

.formula-note em {
  color: var(--text-dim);
  opacity: 0.7;
}
</style>
