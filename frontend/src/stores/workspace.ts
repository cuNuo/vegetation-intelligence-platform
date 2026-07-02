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

const BAND_ORDER = ['blue', 'green', 'red', 'red_edge', 'nir', 'swir1', 'swir2'] as const

const DEFAULT_BAND_MAPPING: Record<string, number> = {
  blue: 1,
  green: 2,
  red: 3,
  red_edge: 0,
  nir: 4,
  swir1: 0,
  swir2: 0,
}

function inferBandMapping(asset: UploadedAsset | null): Record<string, number> {
  if (!asset) return { ...DEFAULT_BAND_MAPPING }
  const count = asset.metadata.count
  return {
    blue: count >= 1 ? 1 : 0,
    green: count >= 2 ? 2 : 0,
    red: count >= 3 ? 3 : 0,
    red_edge: count >= 5 ? 5 : 0,
    nir: count >= 4 ? 4 : 0,
    swir1: count >= 6 ? 6 : 0,
    swir2: count >= 7 ? 7 : 0,
  }
}

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
    availableBands: ['blue', 'green', 'red', 'nir'],
    bandMapping: { ...DEFAULT_BAND_MAPPING } as Record<string, number>,
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
      refreshAssetBands(value[0])
    }
  }

  function selectAsset(value: UploadedAsset) {
    asset.selected = value
    asset.localPath = value.localPath
    refreshAssetBands(value)
  }

  function refreshAssetBands(value: UploadedAsset | null) {
    const mapping = inferBandMapping(value)
    for (const band of BAND_ORDER) {
      asset.bandMapping[band] = mapping[band] ?? 0
    }
    asset.availableBands = BAND_ORDER.filter((band) => asset.bandMapping[band] > 0)
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
    refreshAssetBands,
    togglePanel,
  }
})
