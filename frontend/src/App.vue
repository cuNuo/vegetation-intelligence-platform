<!-- frontend/src/App.vue -->
<!-- 文件说明：应用主壳，编排地图、Agent、任务管理器和统计面板联动。 -->
<script setup lang="ts">
import { defineAsyncComponent, onBeforeUnmount, onMounted, shallowRef } from 'vue'
import AgentDrawer from '@/components/AgentDrawer.vue'
import AppStatusBar from '@/components/AppStatusBar.vue'
import AppToolbar from '@/components/AppToolbar.vue'
import AssetToolbar from '@/components/AssetToolbar.vue'
import IndexCatalog from '@/components/IndexCatalog.vue'
import JobProgressPanel from '@/components/JobProgressPanel.vue'
import { usePlatformApi } from '@/composables/usePlatformApi'
import { useTheme } from '@/composables/useTheme'
import { useWorkspaceStore } from '@/stores/workspace'
import type { JobRecord } from '@/types/platform'

const MapWorkspace = defineAsyncComponent(() => import('@/components/MapWorkspace.vue'))
const StatisticsDashboard = defineAsyncComponent(
  () => import('@/components/StatisticsDashboard.vue'),
)

const store = useWorkspaceStore()
const api = usePlatformApi()
const { theme, toggleTheme } = useTheme()
const opacity = shallowRef(0.78)
let pollTimer: number | undefined

async function refreshSystem() {
  try {
    const [indices, jobs, capabilities] = await Promise.all([
      api.listIndices(),
      api.listJobs(),
      api.getCapabilities(),
    ])
    store.setIndices(indices)
    store.setJobs(jobs)
    store.setCapabilities(capabilities)
    store.setBackendOnline(true)
  } catch {
    store.setBackendOnline(false)
  }
}

async function refreshJobs() {
  try {
    store.setJobs(await api.listJobs())
    store.setBackendOnline(true)
  } catch {
    store.setBackendOnline(false)
  }
}

async function selectJobResult(job: JobRecord, productIndex = 0) {
  const result = job.result ?? await api.getResults(job.id)
  store.setJobs(store.jobs.map((item) => (item.id === job.id ? { ...item, result } : item)))
  store.setActiveResult(result, productIndex)
  navigateTo('workspace')
}

async function cancelJob(job: JobRecord) {
  await api.cancelJob(job.id)
  await refreshJobs()
}

function navigateTo(target: string) {
  const element = target === 'top' ? document.documentElement : document.getElementById(target)
  element?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(async () => {
  await refreshSystem()
  pollTimer = window.setInterval(refreshJobs, 1500)
})

onBeforeUnmount(() => window.clearInterval(pollTimer))
</script>

<template>
  <div class="application">
    <AppToolbar
      :theme="theme"
      :is-backend-online="store.isBackendOnline"
      :is-agent-visible="store.ui.isAgentVisible"
      :is-telemetry-visible="store.ui.isTelemetryVisible"
      :is-catalog-visible="store.ui.isCatalogVisible"
      @toggle-theme="toggleTheme"
      @refresh="refreshSystem"
      @toggle-panel="store.togglePanel"
      @navigate="navigateTo"
    />

    <main class="workspace-shell">
      <section class="workspace-heading">
        <div>
          <span class="kicker">REMOTE SENSING OPERATIONS DESK</span>
          <h1>植被指数智能分析工作台</h1>
        </div>
      </section>

      <AssetToolbar />

      <section
        id="workspace"
        class="primary-grid"
        :class="{ 'agent-collapsed': !store.ui.isAgentVisible }"
      >
        <MapWorkspace
          v-model:opacity="opacity"
          :asset="store.asset.selected"
          :product="store.activeProduct"
          :products="store.activeProducts"
          :active-product-index="store.activeProductIndex"
          @select-product="store.selectActiveProduct"
        />
        <Transition name="panel">
          <AgentDrawer v-if="store.ui.isAgentVisible" />
        </Transition>
      </section>

      <Transition name="panel">
        <section v-if="store.ui.isTelemetryVisible" id="jobs" class="telemetry-grid">
          <JobProgressPanel
            :jobs="store.jobs"
            :active-result="store.activeResult"
            :active-product-index="store.activeProductIndex"
            @select-result="selectJobResult"
            @select-job-product="selectJobResult"
            @select-product="store.selectActiveProduct"
            @cancel-job="cancelJob"
          />
          <StatisticsDashboard
            :products="store.activeProducts"
            :active-index="store.activeProductIndex"
            @select-product="store.selectActiveProduct"
          />
        </section>
      </Transition>

      <Transition name="panel">
        <IndexCatalog
          v-if="store.ui.isCatalogVisible"
          id="catalog"
          :indices="store.indices"
        />
      </Transition>

    </main>

    <AppStatusBar
      :is-backend-online="store.isBackendOnline"
      :capabilities="store.capabilities"
      :running-jobs="store.runningJobs.length"
      :completed-jobs="store.completedJobs.length"
      :active-product="store.activeProduct"
    />
  </div>
</template>

<style scoped>
.application {
  position: fixed;
  inset: 0;
  display: grid;
  width: 100dvw;
  height: 100dvh;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  grid-template-rows: auto minmax(0, 1fr) auto;
  background: var(--surface-0);
}

.workspace-shell {
  display: grid;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  grid-template-rows: auto auto minmax(clamp(500px, calc(100dvh - 300px), 980px), auto) auto auto;
  gap: clamp(8px, 0.8vw, 14px);
  overflow: auto;
  padding: clamp(10px, 1.1vw, 22px);
}

.workspace-heading {
  display: grid;
  align-items: end;
  min-width: 0;
  padding: clamp(8px, 1.2vh, 18px) 0 clamp(4px, 0.8vh, 10px);
}

.kicker {
  color: var(--accent-strong);
  font: 12px var(--font-mono);
}

.workspace-heading h1 {
  margin: 8px 0 0;
  color: var(--text-0);
  font: 500 clamp(30px, 2.4vw, 48px) / 1.08 var(--font-display);
}


.primary-grid {
  display: grid;
  min-width: 0;
  min-height: 0;
  grid-template-columns: minmax(0, 1fr) minmax(clamp(320px, 22vw, 440px), 0.32fr);
  gap: clamp(8px, 0.8vw, 14px);
  scroll-margin-top: 72px;
  transition: grid-template-columns 260ms ease;
}

.primary-grid.agent-collapsed {
  grid-template-columns: minmax(0, 1fr);
}

.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(430px, 100%), 1fr));
  gap: clamp(8px, 0.8vw, 14px);
  min-width: 0;
  scroll-margin-top: 72px;
}

#catalog {
  scroll-margin-top: 72px;
}


.panel-enter-active,
.panel-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (min-width: 1800px) {
  .workspace-shell {
    padding-inline: clamp(18px, 1.4vw, 34px);
  }

  .primary-grid {
    grid-template-columns: minmax(0, 1fr) minmax(400px, 0.26fr);
  }
}

@media (max-width: 1260px) {
  .workspace-heading {
    gap: 10px;
  }
}

@media (max-width: 1100px) {
  .workspace-shell {
    display: flex;
    flex-direction: column;
  }

  .primary-grid {
    min-height: auto;
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .workspace-shell {
    padding: 10px;
  }

  .workspace-heading {
    padding-top: 12px;
  }

}
</style>
