// frontend/src/stores/workspace.ts
// 文件说明：工作台资产、波段映射、任务、结果和界面状态的 Pinia 单一数据源。
import { computed, reactive, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import type {
  AgentPlan,
  IndexMetadata,
  JobRecord,
  Product,
  RasterResult,
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
  const fallbackMapping = {
    blue: count >= 1 ? 1 : 0,
    green: count >= 2 ? 2 : 0,
    red: count >= 3 ? 3 : 0,
    red_edge: count >= 5 ? 5 : 0,
    nir: count >= 4 ? 4 : 0,
    swir1: count >= 6 ? 6 : 0,
    swir2: count >= 7 ? 7 : 0,
  }
  const wavelengthMapping = inferBandMappingByWavelength(asset)
  const descriptions = asset.metadata.descriptions ?? []
  const hasSpectralMetadata =
    (asset.metadata.bandMetadata ?? []).some((band) => band.wavelengthNm !== null)
    || descriptions.some((description) => Boolean(description?.trim()))
  const mapping: Record<string, number> = hasSpectralMetadata
    ? Object.fromEntries(BAND_ORDER.map((band) => [band, 0]))
    : { ...fallbackMapping }
  for (const band of BAND_ORDER) {
    const inferredBand = wavelengthMapping[band]
    if (inferredBand) mapping[band] = inferredBand
  }
  const normalized = descriptions.map((description) =>
    (description ?? '').toLowerCase().replaceAll(/[\s_-]+/g, ''),
  )
  const findBand = (...patterns: RegExp[]) => {
    const index = normalized.findIndex((description) =>
      patterns.some((pattern) => pattern.test(description)),
    )
    return index >= 0 ? index + 1 : 0
  }
  const describedMapping = {
    blue: findBand(/blue/, /^b(?:and)?1$/, /coastalblue/),
    green: findBand(/green/, /^b(?:and)?2$/),
    red: findBand(/^red$/, /^b(?:and)?3$/),
    red_edge: findBand(/rededge/, /rededgenir/, /^re$/),
    nir: findBand(/^nir$/, /nearinfrared/, /^b(?:and)?4$/),
    swir1: findBand(/swir1/, /shortwaveinfrared1/, /^b(?:and)?6$/),
    swir2: findBand(/swir2/, /shortwaveinfrared2/, /^b(?:and)?7$/),
  }
  for (const band of BAND_ORDER) {
    if (!wavelengthMapping[band] && describedMapping[band] > 0) mapping[band] = describedMapping[band]
  }
  return mapping
}

function inferBandMappingByWavelength(asset: UploadedAsset): Partial<Record<string, number>> {
  const bands = asset.metadata.bandMetadata ?? []
  const pick = (min: number, max: number) => {
    const candidates = bands.filter((band) => {
      const wavelength = band.wavelengthNm
      return wavelength !== null && wavelength >= min && wavelength <= max
    })
    if (!candidates.length) return 0
    return candidates[Math.floor(candidates.length / 2)].band
  }
  const mapping: Partial<Record<string, number>> = {}
  const blue = pick(430, 520)
  const green = pick(520, 600)
  const red = pick(620, 700)
  const redEdge = pick(700, 760)
  const nir = pick(760, 900)
  const swir1 = pick(1500, 1800)
  const swir2 = pick(2000, 2400)
  if (blue) mapping.blue = blue
  if (green) mapping.green = green
  if (red) mapping.red = red
  if (redEdge) mapping.red_edge = redEdge
  if (nir) mapping.nir = nir
  if (swir1) mapping.swir1 = swir1
  if (swir2) mapping.swir2 = swir2
  return mapping
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const indices = shallowRef<IndexMetadata[]>([])
  const jobs = shallowRef<JobRecord[]>([])
  const activePlan = shallowRef<AgentPlan | null>(null)
  const activeResult = shallowRef<RasterResult | null>(null)
  const activeProductIndex = shallowRef(0)
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
  const activeProducts = computed(() => activeResult.value?.products ?? [])
  const activeProduct = computed(() => activeProducts.value[activeProductIndex.value] ?? null)
  const bandValidation = computed(() => {
    const sourceCount = asset.selected?.metadata.count ?? 0
    const mappedEntries = Object.entries(asset.bandMapping).filter(([, value]) => value > 0)
    const duplicateBands = mappedEntries
      .map(([, value]) => value)
      .filter((value, index, values) => values.indexOf(value) !== index)
    const invalidBands = mappedEntries.filter(([, value]) => sourceCount > 0 && value > sourceCount)
    const messages: string[] = []
    if (!asset.selected) messages.push('尚未导入影像，当前使用默认4波段映射。')
    if (duplicateBands.length) messages.push(`源波段重复映射: ${[...new Set(duplicateBands)].join(', ')}`)
    if (invalidBands.length) {
      messages.push(`波段号超出源影像范围: ${invalidBands.map(([name]) => name).join(', ')}`)
    }
    if (!asset.bandMapping.red || !asset.bandMapping.nir) {
      messages.push('NDVI/EVI 等常用指数需要 red 与 nir 映射。')
    }
    return {
      valid: messages.length === 0 || messages.every((message) => message.startsWith('尚未导入')),
      messages,
      availableBands: BAND_ORDER.filter((band) => asset.bandMapping[band] > 0),
    }
  })

  function setIndices(value: IndexMetadata[]) {
    indices.value = value
  }

  function setJobs(value: JobRecord[]) {
    jobs.value = value
  }

  function setActivePlan(value: AgentPlan | null) {
    activePlan.value = value
  }

  function setActiveResult(value: RasterResult | null, productIndex = 0) {
    activeResult.value = value
    activeProductIndex.value = Math.min(Math.max(productIndex, 0), Math.max((value?.products.length ?? 1) - 1, 0))
  }

  function setActiveProduct(value: Product | null) {
    setActiveResult(value ? { actualEngine: '', durationSeconds: 0, fallbackReasons: [], products: [value] } : null)
  }

  function selectActiveProduct(index: number) {
    if (!activeResult.value?.products.length) return
    activeProductIndex.value = Math.min(Math.max(index, 0), activeResult.value.products.length - 1)
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

  function setBandMapping(logicalBand: string, sourceBand: number) {
    asset.bandMapping[logicalBand] = sourceBand
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
    activeResult,
    activeProductIndex,
    activeProduct,
    activeProducts,
    capabilities,
    isBackendOnline,
    asset,
    ui,
    runningJobs,
    completedJobs,
    bandValidation,
    setIndices,
    setJobs,
    setActivePlan,
    setActiveResult,
    setActiveProduct,
    selectActiveProduct,
    setCapabilities,
    setBackendOnline,
    addUploadedAssets,
    selectAsset,
    refreshAssetBands,
    setBandMapping,
    togglePanel,
  }
})
