<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: Object,
})

const temporal = computed(() => props.result?.temporal || [])
const hasTemporal = computed(() => temporal.value.length > 0)

// SVG chart dimensions
const SVG_H = 200
const PAD = { top: 16, right: 16, bottom: 48, left: 52 }

const chartData = computed(() => {
  const data = temporal.value
  if (!data.length) return null

  const innerW = 600 // viewBox width minus padding
  const innerH = SVG_H - PAD.top - PAD.bottom

  const fdiValues = data.flatMap((d) => [d.fdi_mean ?? 0, d.fdi_max ?? 0])
  const minFdi = Math.min(...fdiValues)
  const maxFdi = Math.max(...fdiValues)
  const fdiRange = maxFdi - minFdi || 1

  const n = data.length

  function xPos(i) {
    return PAD.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW)
  }
  function yPos(v) {
    return PAD.top + innerH - ((v - minFdi) / fdiRange) * innerH
  }

  function pointsStr(getter) {
    return data.map((d, i) => `${xPos(i)},${yPos(getter(d))}`).join(' ')
  }

  function polylineStr(getter) {
    return data.map((d, i) => `${i === 0 ? 'M' : 'L'}${xPos(i)},${yPos(getter(d))}`).join(' ')
  }

  const labels = data.map((d, i) => ({
    x: xPos(i),
    y: SVG_H - PAD.bottom + 14,
    text: d.date ? String(d.date).slice(5) : String(i + 1), // MM-DD
  }))

  // Y-axis ticks (4 ticks)
  const yTicks = Array.from({ length: 4 }, (_, k) => {
    const v = minFdi + (k / 3) * fdiRange
    return { y: yPos(v), label: v.toFixed(4) }
  })

  const totalW = PAD.left + innerW + PAD.right

  return {
    totalW,
    totalH: SVG_H,
    innerW,
    innerH,
    meanPath: polylineStr((d) => d.fdi_mean ?? 0),
    maxPath: polylineStr((d) => d.fdi_max ?? 0),
    meanPoints: data.map((d, i) => ({ x: xPos(i), y: yPos(d.fdi_mean ?? 0) })),
    maxPoints: data.map((d, i) => ({ x: xPos(i), y: yPos(d.fdi_max ?? 0) })),
    labels,
    yTicks,
    xLeft: PAD.left,
    xRight: PAD.left + innerW,
    yBottom: PAD.top + innerH,
  }
})
</script>

<template>
  <div class="panel-content">
    <div v-if="!hasTemporal" class="panel-empty">
      <div class="empty-state">
        <p>Включите темпоральный анализ</p>
      </div>
    </div>

    <template v-else>
      <div class="section-title">Тренд FDI по датам</div>

      <!-- SVG line chart -->
      <div class="chart-wrap">
        <svg
          v-if="chartData"
          class="trend-svg"
          :viewBox="`0 0 ${chartData.totalW} ${chartData.totalH}`"
          preserveAspectRatio="xMidYMid meet"
        >
          <!-- Grid lines -->
          <line
            v-for="tick in chartData.yTicks"
            :key="tick.label"
            :x1="chartData.xLeft"
            :x2="chartData.xRight"
            :y1="tick.y"
            :y2="tick.y"
            stroke="#1565c0"
            stroke-width="0.5"
            stroke-dasharray="4,3"
          />

          <!-- Y-axis labels -->
          <text
            v-for="tick in chartData.yTicks"
            :key="`yt-${tick.label}`"
            :x="chartData.xLeft - 6"
            :y="tick.y + 4"
            text-anchor="end"
            fill="#90caf9"
            font-size="9"
          >{{ tick.label }}</text>

          <!-- X-axis labels -->
          <text
            v-for="lbl in chartData.labels"
            :key="`xl-${lbl.text}`"
            :x="lbl.x"
            :y="lbl.y"
            text-anchor="middle"
            fill="#90caf9"
            font-size="9"
          >{{ lbl.text }}</text>

          <!-- Axes -->
          <line
            :x1="chartData.xLeft" :x2="chartData.xLeft"
            y1="0" :y2="chartData.yBottom"
            stroke="#1976d2" stroke-width="1"
          />
          <line
            :x1="chartData.xLeft" :x2="chartData.xRight"
            :y1="chartData.yBottom" :y2="chartData.yBottom"
            stroke="#1976d2" stroke-width="1"
          />

          <!-- fdi_max line (red) -->
          <path
            :d="chartData.maxPath"
            fill="none"
            stroke="#ef5350"
            stroke-width="2"
            stroke-linejoin="round"
            stroke-linecap="round"
          />
          <circle
            v-for="(pt, i) in chartData.maxPoints"
            :key="`mx-${i}`"
            :cx="pt.x" :cy="pt.y"
            r="3"
            fill="#ef5350"
          />

          <!-- fdi_mean line (blue) -->
          <path
            :d="chartData.meanPath"
            fill="none"
            stroke="#42a5f5"
            stroke-width="2"
            stroke-linejoin="round"
            stroke-linecap="round"
          />
          <circle
            v-for="(pt, i) in chartData.meanPoints"
            :key="`mn-${i}`"
            :cx="pt.x" :cy="pt.y"
            r="3"
            fill="#42a5f5"
          />
        </svg>

        <!-- Legend -->
        <div class="chart-legend">
          <span class="legend-item mean">fdi_mean</span>
          <span class="legend-item max">fdi_max</span>
        </div>
      </div>

      <!-- Data table -->
      <div class="temporal-table-section">
        <div class="section-title">Данные по датам</div>
        <table class="route-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>FDI mean</th>
              <th>FDI max</th>
              <th>Пластик, %</th>
              <th>Облачность, %</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in temporal" :key="i">
              <td>{{ row.date ?? '—' }}</td>
              <td>{{ row.fdi_mean != null ? row.fdi_mean.toFixed(5) : '—' }}</td>
              <td>{{ row.fdi_max != null ? row.fdi_max.toFixed(5) : '—' }}</td>
              <td>{{ row.plastic_pct != null ? row.plastic_pct.toFixed(4) + '%' : '—' }}</td>
              <td>{{ row.cloud_pct != null ? row.cloud_pct.toFixed(1) + '%' : '—' }}</td>
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

.empty-state {
  text-align: center;
  color: var(--text-dim);
  font-size: 14px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}

.chart-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trend-svg {
  width: 100%;
  height: 200px;
}

.chart-legend {
  display: flex;
  gap: 16px;
  justify-content: center;
  font-size: 11px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-item::before {
  content: '';
  display: inline-block;
  width: 20px;
  height: 3px;
  border-radius: 2px;
}

.legend-item.mean {
  color: #42a5f5;
}

.legend-item.mean::before {
  background: #42a5f5;
}

.legend-item.max {
  color: #ef5350;
}

.legend-item.max::before {
  background: #ef5350;
}

.temporal-table-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}
</style>
