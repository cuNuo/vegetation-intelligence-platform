import { computed, reactive, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import type {
  AgentPlan,
  IndexMetadata,
  JobRecord,
  Product,
  SystemCapabilities,
  UploadedAsset,
} from '@/types/platform'

export const useWorkspaceStore = defineStore('workspace', () => {
  const indices = shallowRef<IndexMetadata[]>([])
  const jobs = shallowRef<JobRecord[]>([])
  const activePlan = shallowRef<AgentPlan | null>(null)
  const activeProduct = shallowRef<Product | null>(null)
  const capabilities = shallowRef<SystemCapabilities | null>(null)
  const isBackendOnline = shallowRef(false)
  const asset = reactive({
    localPath: '',
    selected: null as UploadedAsset | null,
    queue: [] as UploadedAsset[],
    availableBands: ['blue', 'green', 'red', 'red_edge', 'nir', 'swir1', 'swir2'],
    bandMapping: {
      blue: 1,
      green: 2,
      red: 3,
      red_edge: 0,
      nir: 4,
      swir1: 5,
      swir2: 6,
    } as Record<string, number>,
  })
  const ui = reactive({
    isAgentVisible: true,
    isTelemetryVisible: true,
    isCatalogVisible: true,
    isCompact: false,
  })

  const runningJobs = computed(() =>
    jobs.value.filter((job) => ['accepted', 'running'].includes(job.status)),
  )
  const completedJobs = computed(() =>
    jobs.value.filter((job) => job.status === 'successful'),
  )

  function setIndices(value: IndexMetadata[]) {
    indices.value = value
  }

  function setJobs(value: JobRecord[]) {
    jobs.value = value
  }

  function setActivePlan(value: AgentPlan | null) {
    activePlan.value = value
  }

  function setActiveProduct(value: Product | null) {
    activeProduct.value = value
  }

  function setCapabilities(value: SystemCapabilities | null) {
    capabilities.value = value
  }

  function setBackendOnline(value: boolean) {
    isBackendOnline.value = value
  }

  function addUploadedAssets(value: UploadedAsset[]) {
    for (const item of value) {
      const existingIndex = asset.queue.findIndex((assetItem) => assetItem.localPath === item.localPath)
      if (existingIndex >= 0) {
        asset.queue[existingIndex] = item
      } else {
        asset.queue.push(item)
      }
    }
    if (value[0]) {
      asset.selected = value[0]
      asset.localPath = value[0].localPath
    }
  }

  function selectAsset(value: UploadedAsset) {
    asset.selected = value
    asset.localPath = value.localPath
  }

  function togglePanel(panel: 'agent' | 'telemetry' | 'catalog') {
    if (panel === 'agent') ui.isAgentVisible = !ui.isAgentVisible
    if (panel === 'telemetry') ui.isTelemetryVisible = !ui.isTelemetryVisible
    if (panel === 'catalog') ui.isCatalogVisible = !ui.isCatalogVisible
  }

  return {
    indices,
    jobs,
    activePlan,
    activeProduct,
    capabilities,
    isBackendOnline,
    asset,
    ui,
    runningJobs,
    completedJobs,
    setIndices,
    setJobs,
    setActivePlan,
    setActiveProduct,
    setCapabilities,
    setBackendOnline,
    addUploadedAssets,
    selectAsset,
    togglePanel,
  }
})
