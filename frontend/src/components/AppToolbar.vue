<script setup lang="ts">
import type { ThemeMode } from '@/composables/useTheme'

defineProps<{
  theme: ThemeMode
  isBackendOnline: boolean
  isAgentVisible: boolean
  isTelemetryVisible: boolean
  isCatalogVisible: boolean
}>()

const emit = defineEmits<{
  toggleTheme: []
  refresh: []
  togglePanel: [panel: 'agent' | 'telemetry' | 'catalog']
  navigate: [target: string]
}>()

const tools = [
  { id: 'workspace', label: '地图工作台', glyph: '⌖' },
  { id: 'jobs', label: '任务监控', glyph: '▥' },
  { id: 'catalog', label: '指数实验室', glyph: '∿' },
]
</script>

<template>
  <header class="toolbar">
    <button class="brand" type="button" @click="emit('navigate', 'top')">
      <span class="brand-mark">C</span>
      <span class="brand-copy">
        <strong>CANOPY LAB</strong>
        <small>VEGETATION INTELLIGENCE</small>
      </span>
    </button>

    <nav class="primary-tools" aria-label="主工具栏">
      <button
        v-for="tool in tools"
        :key="tool.id"
        type="button"
        @click="emit('navigate', tool.id)"
      >
        <span>{{ tool.glyph }}</span>
        {{ tool.label }}
      </button>
    </nav>

    <div class="view-tools">
      <button
        type="button"
        :class="{ active: isAgentVisible }"
        title="显示或隐藏智能助手"
        @click="emit('togglePanel', 'agent')"
      >
        AI
      </button>
      <button
        type="button"
        :class="{ active: isTelemetryVisible }"
        title="显示或隐藏任务与统计面板"
        @click="emit('togglePanel', 'telemetry')"
      >
        状态
      </button>
      <button
        type="button"
        :class="{ active: isCatalogVisible }"
        title="显示或隐藏指数实验室"
        @click="emit('togglePanel', 'catalog')"
      >
        指数
      </button>
      <span class="tool-divider" />
      <button type="button" title="刷新服务状态" @click="emit('refresh')">↻</button>
      <button
        class="theme-toggle"
        type="button"
        :aria-label="theme === 'dark' ? '切换到白天模式' : '切换到夜晚模式'"
        @click="emit('toggleTheme')"
      >
        <span>{{ theme === 'dark' ? '☀' : '☾' }}</span>
        {{ theme === 'dark' ? '白天' : '夜晚' }}
      </button>
      <span class="api-indicator" :class="{ offline: !isBackendOnline }">
        {{ isBackendOnline ? 'API 在线' : 'API 离线' }}
      </span>
    </div>
  </header>
</template>

<style scoped>
.toolbar {
  position: sticky;
  z-index: 30;
  top: 0;
  display: flex;
  min-width: 0;
  min-height: 58px;
  align-items: center;
  gap: clamp(8px, 1vw, 18px);
  padding: 0 clamp(10px, 1.4vw, 28px);
  border-bottom: 1px solid var(--border-strong);
  background: color-mix(in srgb, var(--surface-0) 88%, transparent);
  box-shadow: 0 8px 30px var(--shadow-soft);
  backdrop-filter: blur(18px);
}

.brand,
.primary-tools button,
.view-tools button {
  border: 0;
  background: transparent;
  color: var(--text-1);
  cursor: pointer;
}

.brand {
  display: flex;
  min-width: 0;
  flex: 0 1 260px;
  align-items: center;
  justify-self: start;
  gap: 10px;
  padding: 0;
}

.brand-mark {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid var(--accent);
  color: var(--accent);
  font: 18px var(--font-display);
  transform: rotate(-8deg);
}

.brand-copy {
  min-width: 0;
  text-align: left;
}

.brand-copy strong,
.brand-copy small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brand-copy strong {
  font: 600 16px var(--font-display);
}

.brand-copy small {
  margin-top: 2px;
  color: var(--text-3);
  font: 11px var(--font-mono);
}

.primary-tools,
.view-tools {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
}

.primary-tools {
  flex: 1 1 auto;
  justify-content: center;
}

.primary-tools button,
.view-tools button {
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid transparent;
  font-size: 14px;
  white-space: nowrap;
}

.primary-tools button:hover,
.view-tools button:hover,
.view-tools button.active {
  border-color: var(--border-strong);
  background: var(--surface-hover);
  color: var(--accent-strong);
}

.primary-tools button span {
  margin-right: 5px;
  color: var(--accent);
  font-family: var(--font-mono);
}

.view-tools {
  flex: 0 1 auto;
  justify-content: flex-end;
  overflow: hidden;
}

.tool-divider {
  width: 1px;
  height: 22px;
  margin: 0 4px;
  background: var(--border);
}

.theme-toggle {
  min-width: 70px;
}

.theme-toggle span {
  margin-right: 4px;
  font-size: 13px;
}

.api-indicator {
  margin-left: 6px;
  padding: 6px 8px;
  border: 1px solid var(--success-border);
  color: var(--success);
  font: 12px var(--font-mono);
  white-space: nowrap;
}

.api-indicator.offline {
  border-color: var(--danger-border);
  color: var(--danger);
}

@media (max-width: 1160px) {
  .primary-tools {
    display: none;
  }

  .brand {
    flex-basis: auto;
  }

  .view-tools {
    margin-left: auto;
  }
}

@media (max-width: 720px) {
  .toolbar {
    min-height: 52px;
  }

  .brand-copy small,
  .view-tools > button:nth-child(-n + 3),
  .tool-divider,
  .api-indicator {
    display: none;
  }
}

@media (max-width: 420px) {
  .brand-copy strong {
    max-width: 118px;
  }

  .theme-toggle {
    min-width: 0;
  }
}
</style>
