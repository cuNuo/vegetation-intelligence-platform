<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, shallowRef } from 'vue'
import type { Product, SystemCapabilities } from '@/types/platform'

const props = defineProps<{
  isBackendOnline: boolean
  capabilities: SystemCapabilities | null
  runningJobs: number
  completedJobs: number
  activeProduct: Product | null
}>()

const now = shallowRef(new Date())
let timer: number | undefined

const engineLabel = computed(() =>
  props.capabilities?.engines.map((engine) => engine.toUpperCase()).join(' / ') ?? '检测中',
)

onMounted(() => {
  timer = window.setInterval(() => {
    now.value = new Date()
  }, 1000)
})

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <footer class="status-bar">
    <div class="status-group">
      <span class="status-light" :class="{ offline: !isBackendOnline }" />
      <strong>{{ isBackendOnline ? '服务正常' : '服务离线' }}</strong>
      <span>OGC API · Processes</span>
    </div>
    <div class="status-group">
      <span>计算引擎</span>
      <strong>{{ engineLabel }}</strong>
      <span v-if="capabilities?.cuda" class="cuda">CUDA READY</span>
      <span v-else>CPU FALLBACK</span>
    </div>
    <div class="status-group">
      <span>指数库</span>
      <strong>
        {{ capabilities?.totalIndexCount ?? capabilities?.indexCount ?? 35 }} 个
      </strong>
      <span>{{ capabilities?.customIndexStorage ?? 'memory' }}</span>
      <span v-if="capabilities?.customIndexCount">+{{ capabilities.customIndexCount }} 自定义</span>
    </div>
    <div class="status-group">
      <span>队列</span>
      <strong>{{ runningJobs }} 运行 / {{ completedJobs }} 完成</strong>
    </div>
    <div class="status-group product-status">
      <span>当前结果</span>
      <strong>{{ activeProduct?.name ?? '未选择' }}</strong>
      <span v-if="activeProduct">{{ activeProduct.crs ?? '无CRS' }}</span>
    </div>
    <div class="status-group clock">
      <span>{{ now.toLocaleDateString('zh-CN') }}</span>
      <strong>{{ now.toLocaleTimeString('zh-CN', { hour12: false }) }}</strong>
    </div>
  </footer>
</template>

<style scoped>
.status-bar {
  position: relative;
  z-index: 40;
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 34px;
  align-items: center;
  border-top: 1px solid var(--border-strong);
  background: color-mix(in srgb, var(--surface-0) 94%, transparent);
  color: var(--text-3);
  font: 12px var(--font-mono);
  overflow: hidden;
  backdrop-filter: blur(18px);
}

.status-group {
  display: flex;
  min-width: 0;
  height: 34px;
  align-items: center;
  gap: 7px;
  padding: 0 13px;
  border-right: 1px solid var(--border);
  white-space: nowrap;
}

.status-group strong {
  overflow: hidden;
  color: var(--text-1);
  font-weight: 600;
  text-overflow: ellipsis;
}

.status-light {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 8px var(--success);
}

.status-light.offline {
  background: var(--danger);
  box-shadow: 0 0 8px var(--danger);
}

.cuda {
  color: var(--accent-strong);
}

.product-status {
  flex: 1;
}

.clock {
  margin-left: auto;
  border-right: 0;
}

@media (max-width: 900px) {
  .status-group:nth-child(2),
  .product-status {
    display: none;
  }
}

@media (max-width: 560px) {
  .status-group:first-child span:last-child,
  .clock span {
    display: none;
  }
}
</style>
