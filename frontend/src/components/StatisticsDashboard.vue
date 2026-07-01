<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  shallowRef,
  useTemplateRef,
  watch,
} from 'vue'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { type EChartsType, init, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import type { Product } from '@/types/platform'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  product: Product | null
}>()

const chartContainer = useTemplateRef<HTMLDivElement>('chartContainer')
const chart = shallowRef<EChartsType | null>(null)
const stats = computed(() => props.product?.statistics)
let resizeObserver: ResizeObserver | undefined
let themeObserver: MutationObserver | undefined

async function renderChart() {
  await nextTick()
  if (!chartContainer.value || !stats.value) return
  chart.value ??= init(chartContainer.value)
  if (!resizeObserver) {
    resizeObserver = new ResizeObserver(() => chart.value?.resize())
    resizeObserver.observe(chartContainer.value)
  }
  if (!themeObserver) {
    themeObserver = new MutationObserver(renderChart)
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
  }
  const styles = getComputedStyle(document.documentElement)
  const textColor = styles.getPropertyValue('--text-3').trim()
  const borderColor = styles.getPropertyValue('--border').trim()
  const accentColor = styles.getPropertyValue('--accent').trim()
  const accentBase = styles.getPropertyValue('--accent-strong').trim()
  chart.value.setOption({
    grid: { left: 12, right: 8, top: 15, bottom: 18, containLabel: true },
    xAxis: {
      type: 'category',
      data: stats.value.histogram.edges.slice(0, -1).map((value) => value.toFixed(2)),
      axisLabel: { color: textColor, fontSize: 11, interval: 4 },
      axisLine: { lineStyle: { color: borderColor } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: textColor, fontSize: 11 },
      splitLine: { lineStyle: { color: borderColor } },
    },
    series: [
      {
        type: 'bar',
        data: stats.value.histogram.counts,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 1,
            x2: 0,
            y2: 0,
            colorStops: [
              { offset: 0, color: accentBase },
              { offset: 1, color: accentColor },
            ],
          },
        },
      },
    ],
    tooltip: { trigger: 'axis' },
  })
}

watch(() => props.product, renderChart)
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  themeObserver?.disconnect()
  chart.value?.dispose()
})
</script>

<template>
  <section class="stats-panel">
    <header>
      <span>PIXEL DISTRIBUTION</span>
      <h2>{{ product?.name ?? '结果统计' }}</h2>
    </header>
    <div v-if="stats" class="stats-content">
      <div class="metric-grid">
        <div>
          <span>平均值</span>
          <strong>{{ stats.mean?.toFixed(4) ?? '—' }}</strong>
        </div>
        <div>
          <span>标准差</span>
          <strong>{{ stats.standardDeviation?.toFixed(4) ?? '—' }}</strong>
        </div>
        <div>
          <span>有效像元</span>
          <strong>{{ stats.validPixels.toLocaleString() }}</strong>
        </div>
      </div>
      <div ref="chartContainer" class="chart" />
    </div>
    <div v-else class="stats-empty">完成计算后显示指数直方图和区域统计</div>
  </section>
</template>

<style scoped>
.stats-panel {
  min-width: 0;
  min-height: 290px;
  padding: 22px;
  border: 1px solid var(--border-strong);
  background: var(--surface-1);
}

.stats-panel header span {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
}

.stats-panel h2 {
  margin: 5px 0 15px;
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 500;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.metric-grid div {
  padding: 9px;
  border: 1px solid var(--border);
  background: var(--surface-2);
}

.metric-grid span,
.metric-grid strong {
  display: block;
}

.metric-grid span {
  color: var(--muted);
  font-size: 12px;
}

.metric-grid strong {
  margin-top: 5px;
  color: var(--text-1);
  font-family: var(--font-mono);
  font-size: 14px;
}

.chart {
  height: 180px;
  margin-top: 8px;
}

.stats-empty {
  display: grid;
  min-height: 190px;
  place-items: center;
  border: 1px dashed var(--border-strong);
  color: var(--muted);
  font-size: 13px;
}
</style>
