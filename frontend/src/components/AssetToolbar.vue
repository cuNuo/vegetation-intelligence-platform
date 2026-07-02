<!-- frontend/src/components/AssetToolbar.vue -->
<!-- 文件说明：影像资产与波段映射工具栏。 -->
<!-- 主要职责：上传 GeoTIFF、跟踪进度、编辑波段映射并提交批量任务。 -->
<!-- 对外约定：workspace store 与 Platform API。 -->
<!-- 依赖边界：文件读取和提交错误必须反馈到 store。 -->

<script setup lang="ts">
import { computed, shallowRef, useTemplateRef } from 'vue'
import { usePlatformApi } from '@/composables/usePlatformApi'
import { useWorkspaceStore } from '@/stores/workspace'
import type { UploadedAsset } from '@/types/platform'

const store = useWorkspaceStore()
const api = usePlatformApi()
const fileInput = useTemplateRef<HTMLInputElement>('fileInput')
const isDragging = shallowRef(false)
const isUploading = shallowRef(false)
const isSubmittingBatch = shallowRef(false)
const isMappingOpen = shallowRef(false)
const isIndexExtractionOpen = shallowRef(false)
const indexSearchQuery = shallowRef('')
const activeIndexCategory = shallowRef('all')
const selectedManualIndexIds = shallowRef<string[]>([])
const uploadingFileName = shallowRef('')
const currentUploadProgress = shallowRef(0)
const totalUploadProgress = shallowRef(0)
const uploadStage = shallowRef<
  'idle' | 'uploading' | 'received' | 'metadata' | 'pyramid' | 'preview' | 'located'
>('idle')
const message = shallowRef('选择或拖入GeoTIFF，系统会保存到后端输入目录')
const bandLabels: Record<string, string> = {
  blue: 'Blue',
  green: 'Green',
  red: 'Red',
  red_edge: 'Red Edge',
  nir: 'NIR',
  swir1: 'SWIR 1',
  swir2: 'SWIR 2',
}

const mappedBandCount = computed(
  () => Object.values(store.asset.bandMapping).filter((band) => band > 0).length,
)
const selectedAsset = computed(() => store.asset.selected)
const sourceBandOptions = computed(() => {
  const count = selectedAsset.value?.metadata.count ?? 0
  return Array.from({ length: count }, (_, index) => index + 1)
})
const sourceBandDetails = computed(() =>
  (selectedAsset.value?.metadata.bandMetadata ?? []).map((band) => ({
    ...band,
    label: `Band ${band.band}`,
    detail: [
      band.wavelengthNm ? `${Math.round(band.wavelengthNm)} nm` : '',
      band.description ?? '',
    ].filter(Boolean).join(' / ') || '无波长或描述元数据',
  })),
)
const hasWavelengthMetadata = computed(() =>
  sourceBandDetails.value.some((band) => band.wavelengthNm !== null),
)
const bandRows = computed(() =>
  Object.keys(bandLabels).map((key) => ({
    key,
    label: bandLabels[key],
    value: store.asset.bandMapping[key] ?? 0,
  })),
)
const indexCategories = computed(() => [
  ...new Set(store.indices.flatMap((index) => index.categories)),
].sort((left, right) => left.localeCompare(right)))
const indexSelectionCards = computed(() =>
  store.indices.map((index) => {
    const missingBands = index.requiredBands.filter(
      (band) => !store.asset.availableBands.includes(band),
    )
    return {
      ...index,
      missingBands,
      disabled: missingBands.length > 0,
      selected: selectedManualIndexIds.value.includes(index.id),
    }
  }),
)
const filteredIndexCards = computed(() => {
  const keyword = indexSearchQuery.value.trim().toLowerCase()
  return indexSelectionCards.value.filter((index) => {
    const matchesCategory =
      activeIndexCategory.value === 'all' || index.categories.includes(activeIndexCategory.value)
    const haystack = [
      index.id,
      index.name,
      index.formula,
      index.description,
      ...index.recommendationTags,
      ...index.categories,
    ].join(' ').toLowerCase()
    return matchesCategory && (!keyword || haystack.includes(keyword))
  })
})
const selectedManualIndices = computed(() =>
  store.indices.filter((index) => selectedManualIndexIds.value.includes(index.id)),
)
const executableFilteredIndexCount = computed(() =>
  filteredIndexCards.value.filter((index) => !index.disabled).length,
)
const uploadStageLabel = computed(() => {
  const labels = {
    idle: '等待影像',
    uploading: '上传中',
    received: '后端接收完成',
    metadata: '读取元数据',
    pyramid: '检查/创建影像金字塔',
    preview: '生成预览/瓦片就绪',
    located: '已定位',
  }
  return labels[uploadStage.value]
})
const pyramidLevels = computed(() => {
  const asset = selectedAsset.value
  if (!asset) return []
  return (asset.metadata.overviewLevels ?? []).slice(0, 6).map((factor, index) => (
    `L${index + 1} ${Math.ceil(asset.metadata.width / factor)}×${Math.ceil(asset.metadata.height / factor)}`
  ))
})
const pyramidStatusLabel = computed(() => {
  const status = selectedAsset.value?.metadata.overviewStatus
  if (status === 'built') return '首次导入已创建内部金字塔'
  if (status === 'reused') return '已复用影像自带金字塔'
  if (status === 'not-needed') return '小影像无需额外金字塔'
  return '等待影像'
})

/** 打开隐藏文件选择器。 */
function openPicker() {
  fileInput.value?.click()
}

/** 串行上传选择的 GeoTIFF，并逐文件更新进度和资产列表。 */
async function uploadFiles(files: FileList | File[]) {
  const geotiffs = Array.from(files).filter((file) => /\.tiff?$/i.test(file.name))
  if (!geotiffs.length) {
    message.value = '未发现.tif或.tiff影像文件'
    return
  }
  isUploading.value = true
  currentUploadProgress.value = 0
  totalUploadProgress.value = 0
  uploadStage.value = 'uploading'
  message.value = `正在上传 ${geotiffs.length} 个影像…`
  try {
    const uploaded: UploadedAsset[] = []
    for (const [index, file] of geotiffs.entries()) {
      uploadingFileName.value = file.name
      uploaded.push(await api.uploadAsset(file, (progress) => {
        currentUploadProgress.value = progress
        totalUploadProgress.value = Math.round(((index + progress / 100) / geotiffs.length) * 100)
        if (progress >= 100) {
          uploadStage.value = 'pyramid'
          message.value = `正在读取元数据并检查影像金字塔：${file.name}（${index + 1}/${geotiffs.length}）`
          return
        }
        uploadStage.value = 'uploading'
        message.value = `正在上传 ${file.name}：${progress}%（${index + 1}/${geotiffs.length}）`
      }))
      uploadStage.value = 'preview'
      const overviewStatus = uploaded[uploaded.length - 1]?.metadata.overviewStatus
      if (overviewStatus === 'built') {
        message.value = `影像金字塔与预览已创建：${file.name}`
      } else if (overviewStatus === 'reused') {
        message.value = `已复用影像金字塔，预览与瓦片入口就绪：${file.name}`
      } else {
        message.value = `影像无需额外金字塔，预览与瓦片入口就绪：${file.name}`
      }
    }
    uploadStage.value = 'received'
    store.addUploadedAssets(uploaded)
    totalUploadProgress.value = 100
    uploadStage.value = 'located'
    message.value = uploaded.length > 1
      ? `已导入 ${uploaded.length} 个影像`
      : `已导入 ${uploaded[0]?.filename ?? '影像'}`
  } catch (error) {
    uploadStage.value = 'idle'
    message.value = error instanceof Error ? error.message : '影像上传失败'
  } finally {
    isUploading.value = false
    uploadingFileName.value = ''
  }
}

/** 处理文件选择器变更并清空 input 以允许重复选择。 */
function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) void uploadFiles(input.files)
  input.value = ''
}

/** 处理拖拽文件并复用统一上传流程。 */
function onDrop(event: DragEvent) {
  isDragging.value = false
  if (event.dataTransfer?.files) void uploadFiles(event.dataTransfer.files)
}

/** 打开手动植被指数提取弹窗，并按当前方案或 NDVI 初始化选择。 */
function openIndexExtraction() {
  if (!store.asset.queue.length) {
    message.value = '请先导入至少一个GeoTIFF影像'
    return
  }
  if (!store.indices.length) {
    message.value = '指数目录尚未加载完成，请先刷新服务状态'
    return
  }
  const availableIds = new Set(indexSelectionCards.value.filter((index) => !index.disabled).map((index) => index.id))
  const planIds = store.activePlan?.selectedIndices.filter((indexId) => availableIds.has(indexId)) ?? []
  const defaultIds = planIds.length
    ? planIds
    : availableIds.has('ndvi')
      ? ['ndvi']
      : [...availableIds].slice(0, 1)
  selectedManualIndexIds.value = defaultIds
  indexSearchQuery.value = ''
  activeIndexCategory.value = 'all'
  isIndexExtractionOpen.value = true
}

/** 校验后提交用户在弹窗中手动选择的指数。 */
async function submitManualIndexExtraction() {
  if (!selectedManualIndexIds.value.length) {
    message.value = '请至少选择一个可执行指数'
    return
  }
  await submitSelectedIndices(selectedManualIndexIds.value)
  isIndexExtractionOpen.value = false
}

/** 把一组指数提交给当前批量队列，任务管理器由全局轮询刷新。 */
async function submitSelectedIndices(indices: string[]) {
  if (!store.asset.queue.length) {
    message.value = '请先导入至少一个GeoTIFF影像'
    return
  }
  isSubmittingBatch.value = true
  message.value = `正在提交 ${store.asset.queue.length} 个影像的 ${indices.length} 个指数任务…`
  try {
    for (const asset of store.asset.queue) {
      await api.executeAssetBatch(
        asset.localPath,
        indices,
        store.asset.bandMapping,
        store.activePlan?.engine ?? 'auto',
      )
    }
    message.value = `已提交 ${store.asset.queue.length} 个异步任务，任务管理器将自动刷新`
  } catch (error) {
    message.value = error instanceof Error ? error.message : '批量任务提交失败'
  } finally {
    isSubmittingBatch.value = false
  }
}

/** 在手动提取弹窗里切换单个指数，缺失波段的指数不可选。 */
function toggleManualIndex(indexId: string) {
  const card = indexSelectionCards.value.find((item) => item.id === indexId)
  if (!card || card.disabled) return
  selectedManualIndexIds.value = card.selected
    ? selectedManualIndexIds.value.filter((item) => item !== indexId)
    : [...selectedManualIndexIds.value, indexId]
}

/** 选择当前搜索和分类结果中的全部可执行指数。 */
function selectVisibleExecutableIndices() {
  const visibleIds = filteredIndexCards.value
    .filter((index) => !index.disabled)
    .map((index) => index.id)
  selectedManualIndexIds.value = [...new Set([...selectedManualIndexIds.value, ...visibleIds])]
}

/** 把逻辑波段名转换成弹窗可读标签。 */
function formatBandName(band: string) {
  return bandLabels[band] ?? band
}

/** 把下拉框选择写回逻辑波段映射。 */
function updateBandMapping(logicalBand: string, event: Event) {
  const select = event.target as HTMLSelectElement
  store.setBandMapping(logicalBand, Number(select.value))
}

/** 检查当前方案所需波段是否全部有效映射。 */
function validateBandMapping() {
  if (!hasWavelengthMetadata.value && selectedAsset.value) {
    message.value = '该影像未提供波长元数据，已按常见多光谱顺序兜底；请在弹窗中人工核对。'
    return
  }
  if (store.bandValidation.valid) {
    message.value = `波段映射可用：${store.asset.availableBands.join(' / ')}`
    return
  }
  message.value = store.bandValidation.messages.join('；')
}
</script>

<template>
  <section
    class="asset-toolbar"
    :class="{ dragging: isDragging }"
    aria-label="影像资产工具栏"
    @dragenter.prevent="isDragging = true"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="fileInput"
      class="file-input"
      type="file"
      accept=".tif,.tiff,image/tiff"
      multiple
      @change="onFileChange"
    />

    <div class="asset-import-card">
      <div class="thumbnail" :class="{ empty: !selectedAsset }">
        <span v-if="selectedAsset">{{ selectedAsset.filename.slice(0, 2).toUpperCase() }}</span>
        <span v-else>TIFF</span>
        <i v-for="level in 4" :key="level" />
      </div>
      <div class="asset-copy">
        <span class="eyebrow">RASTER INTAKE</span>
        <strong>{{ selectedAsset?.filename ?? '尚未导入影像' }}</strong>
        <p>
          {{ isUploading
            ? `${uploadStageLabel}：${currentUploadProgress}%${uploadingFileName ? ` / ${uploadingFileName}` : ''}`
            : message }}
        </p>
        <div v-if="isUploading || totalUploadProgress > 0" class="upload-progress">
          <span :style="{ width: `${totalUploadProgress}%` }" />
        </div>
      </div>
      <button class="primary-action" :disabled="isUploading" @click="openPicker">
        {{ isUploading ? '上传中…' : '选择影像' }}
      </button>
    </div>

    <div class="asset-stat queue-panel">
      <span>批量队列</span>
      <strong>{{ store.asset.queue.length }} 个影像</strong>
      <div class="queue-list" aria-label="已导入影像列表">
        <button
          v-for="asset in store.asset.queue.slice(0, 4)"
          :key="asset.localPath"
          :class="{ active: asset.localPath === selectedAsset?.localPath }"
          @click="store.selectAsset(asset)"
        >
          {{ asset.filename }}
        </button>
      </div>
    </div>

    <div class="asset-stat">
      <span>缩略图金字塔</span>
      <strong>{{ pyramidLevels.length ? pyramidLevels.join(' / ') : pyramidStatusLabel }}</strong>
      <small>{{ pyramidStatusLabel }}；计算仍使用原始分辨率</small>
    </div>

    <button type="button" class="asset-stat mapping-entry" @click="isMappingOpen = true">
      <span>逻辑波段</span>
      <strong>{{ mappedBandCount }} / 7 已映射</strong>
      <small>
        {{ store.bandValidation.valid ? '自动识别，点击修正' : '映射需要检查' }}
      </small>
    </button>

    <button
      class="batch-action"
      :disabled="isSubmittingBatch || isUploading || !store.asset.queue.length"
      @click="openIndexExtraction"
    >
      {{ isSubmittingBatch ? '提交中…' : '植被指数提取' }}
    </button>

    <div v-if="isMappingOpen" class="modal-backdrop" @click.self="isMappingOpen = false">
      <section class="band-mapping-modal" role="dialog" aria-modal="true" aria-label="波段映射">
        <header class="mapping-header">
          <div>
            <span>波段映射</span>
            <strong>{{ store.bandValidation.valid ? '映射可用' : '需要检查' }}</strong>
          </div>
          <button type="button" class="close-button" @click="isMappingOpen = false">×</button>
        </header>
        <div class="mapping-summary">
          <span>
            {{
              selectedAsset
                ? selectedAsset.metadata.bandInferenceSource === 'filename-profile'
                  ? `${selectedAsset.metadata.sensor}，已依据原始数据配置自动映射`
                  : hasWavelengthMetadata
                  ? `${selectedAsset.metadata.count} 个源波段，已优先按波长自动映射`
                  : `${selectedAsset.metadata.count} 个源波段，无波长元数据，按常见顺序兜底`
                : '尚未导入影像'
            }}
          </span>
          <button type="button" @click="validateBandMapping">验证映射</button>
        </div>
        <div class="band-grid">
          <label v-for="band in bandRows" :key="band.key">
            <span>{{ band.label }}</span>
            <select :value="band.value" :disabled="!selectedAsset" @change="updateBandMapping(band.key, $event)">
              <option value="0">未映射</option>
              <option v-for="sourceBand in sourceBandOptions" :key="sourceBand" :value="sourceBand">
                Band {{ sourceBand }}
              </option>
            </select>
          </label>
        </div>
        <div v-if="sourceBandDetails.length" class="source-band-list">
          <span v-for="band in sourceBandDetails" :key="band.band">
            {{ band.label }}: {{ band.detail }}
          </span>
        </div>
        <p v-if="store.bandValidation.messages.length">
          {{ store.bandValidation.messages.join('；') }}
        </p>
        <button type="button" class="save-mapping-button" @click="isMappingOpen = false">完成</button>
      </section>
    </div>

    <div v-if="isIndexExtractionOpen" class="modal-backdrop" @click.self="isIndexExtractionOpen = false">
      <section class="index-extraction-modal" role="dialog" aria-modal="true" aria-label="植被指数提取">
        <header class="mapping-header">
          <div>
            <span>植被指数提取</span>
            <strong>{{ selectedManualIndexIds.length }} 个指数已选择</strong>
          </div>
          <button type="button" class="close-button" @click="isIndexExtractionOpen = false">×</button>
        </header>

        <div class="index-submit-summary">
          <span>{{ store.asset.queue.length }} 个影像将提交到任务管理器</span>
          <span>{{ mappedBandCount }} / 7 个逻辑波段已映射</span>
          <span>{{ executableFilteredIndexCount }} 个当前筛选结果可执行</span>
        </div>

        <div class="index-filter-bar">
          <label>
            <span>搜索指数</span>
            <input
              v-model="indexSearchQuery"
              type="search"
              placeholder="输入 NDVI、叶绿素、water、公式关键词"
            />
          </label>
          <label>
            <span>分类筛选</span>
            <select v-model="activeIndexCategory">
              <option value="all">全部分类</option>
              <option v-for="category in indexCategories" :key="category" :value="category">
                {{ category }}
              </option>
            </select>
          </label>
        </div>

        <div class="index-dialog-actions">
          <button type="button" @click="selectVisibleExecutableIndices">选择当前可执行</button>
          <button type="button" @click="selectedManualIndexIds = []">清空选择</button>
        </div>

        <div class="manual-index-grid" aria-label="可选植被指数">
          <button
            v-for="index in filteredIndexCards"
            :key="index.id"
            type="button"
            :class="{ selected: index.selected, disabled: index.disabled }"
            :disabled="index.disabled"
            @click="toggleManualIndex(index.id)"
          >
            <span class="manual-index-code">{{ index.id.toUpperCase() }}</span>
            <strong>{{ index.name }}</strong>
            <small>{{ index.formula }}</small>
            <em v-if="index.disabled">
              缺少 {{ index.missingBands.map(formatBandName).join(' / ') }}
            </em>
            <em v-else>
              可执行 · {{ index.categories.slice(0, 2).join(' / ') || '未分类' }}
            </em>
          </button>
        </div>

        <div v-if="selectedManualIndices.length" class="selected-index-strip">
          <span v-for="index in selectedManualIndices" :key="index.id">
            {{ index.id.toUpperCase() }}
          </span>
        </div>

        <button
          type="button"
          class="save-mapping-button submit-index-button"
          :disabled="isSubmittingBatch || !selectedManualIndexIds.length"
          @click="submitManualIndexExtraction"
        >
          {{ isSubmittingBatch ? '提交中…' : '提交任务' }}
        </button>
      </section>
    </div>
  </section>
</template>

<style scoped>
.asset-toolbar {
  position: relative;
  z-index: 10;
  display: grid;
  grid-template-columns: minmax(min(100%, 460px), 1.45fr) repeat(3, minmax(min(100%, 180px), 0.7fr)) minmax(min(100%, 180px), 0.5fr);
  gap: 1px;
  min-width: 0;
  height: max-content;
  min-height: clamp(88px, 8dvh, 108px);
  grid-auto-rows: minmax(clamp(88px, 8dvh, 108px), auto);
  overflow: visible;
  border: 1px solid var(--border);
  background: var(--border);
  transition: border-color 160ms ease, box-shadow 160ms ease;
}

.asset-toolbar.dragging {
  border-color: var(--accent-strong);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent);
}

.file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}

.asset-import-card,
.asset-stat,
.batch-action {
  min-width: 0;
  background: var(--surface-1);
}

.asset-import-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: clamp(10px, 1vw, 14px);
  padding: 10px 12px;
}

.thumbnail {
  position: relative;
  display: grid;
  width: clamp(42px, 3.2vw, 52px);
  height: clamp(42px, 3.2vw, 52px);
  place-items: center;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 28%, transparent), transparent),
    var(--surface-2);
  color: var(--acid);
  font: 700 10px var(--font-mono);
}

.thumbnail.empty {
  color: var(--text-3);
}

.thumbnail i {
  position: absolute;
  border: 1px solid color-mix(in srgb, var(--accent) 24%, transparent);
  transform: rotate(2deg);
}

.thumbnail i:nth-child(2) { inset: 8px; }
.thumbnail i:nth-child(3) { inset: 14px; }
.thumbnail i:nth-child(4) { inset: 20px; }
.thumbnail i:nth-child(5) { inset: 26px; }

.asset-copy {
  min-width: 0;
}

.eyebrow,
.asset-stat span {
  display: block;
  margin-bottom: 5px;
  color: var(--text-3);
  font: 12px var(--font-mono);
}

.asset-copy strong,
.asset-stat strong {
  display: block;
  overflow: hidden;
  color: var(--text-1);
  font: 14px var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-copy p,
.asset-stat small {
  display: block;
  margin: 5px 0 0;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.45;
}

.asset-copy p {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-stat small {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.upload-progress {
  height: 5px;
  margin-top: 6px;
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--surface-2);
}

.upload-progress span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent-strong), var(--accent));
  transition: width 180ms ease;
}

.primary-action,
.batch-action,
.queue-list button {
  border: 1px solid var(--border-strong);
  background: var(--surface-2);
  color: var(--text-1);
  cursor: pointer;
}

.primary-action {
  padding: 10px 14px;
  color: var(--acid);
  font: 700 13px var(--font-mono);
  white-space: nowrap;
}

.asset-stat {
  display: grid;
  align-content: center;
  gap: 4px;
  padding: 10px 12px;
}

.queue-list {
  display: flex;
  gap: 5px;
  margin-top: 8px;
  overflow: hidden;
}

.queue-list button {
  max-width: 88px;
  padding: 4px 6px;
  overflow: hidden;
  color: var(--text-3);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-list button.active {
  border-color: var(--accent-strong);
  color: var(--acid);
}

.batch-action {
  padding: 10px 16px;
  color: var(--surface-0);
  background: var(--accent-strong);
  font: 800 13px var(--font-mono);
}

.mapping-entry {
  border: 0;
  text-align: left;
  cursor: pointer;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: clamp(16px, 4vw, 36px);
  background: rgba(3, 9, 15, 0.62);
}

.band-mapping-modal {
  display: grid;
  gap: 14px;
  width: min(860px, 100%);
  max-height: min(720px, calc(100dvh - 32px));
  min-width: 0;
  overflow: auto;
  border: 1px solid var(--border-strong);
  background: var(--surface-0);
  box-shadow: 0 22px 80px rgba(0, 0, 0, 0.32);
  padding: clamp(16px, 2vw, 22px);
}

.index-extraction-modal {
  display: grid;
  gap: 14px;
  width: min(980px, 100%);
  max-height: min(780px, calc(100dvh - 32px));
  min-width: 0;
  overflow: auto;
  border: 1px solid var(--border-strong);
  background: var(--surface-0);
  box-shadow: 0 22px 80px rgba(0, 0, 0, 0.32);
  padding: clamp(16px, 2vw, 22px);
}

.mapping-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.mapping-header span {
  display: block;
  color: var(--text-3);
  font: 12px var(--font-mono);
}

.mapping-header strong {
  display: block;
  margin-top: 4px;
  color: var(--text-1);
  font: 14px var(--font-mono);
}

.close-button,
.mapping-summary button,
.save-mapping-button {
  min-height: 32px;
  padding: 6px 10px;
  border: 1px solid var(--border-strong);
  background: var(--surface-2);
  color: var(--acid);
  font: 700 12px var(--font-mono);
  cursor: pointer;
}

.mapping-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.mapping-summary span {
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.5;
}

.index-submit-summary,
.index-dialog-actions,
.selected-index-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.index-submit-summary span,
.selected-index-strip span {
  border: 1px solid var(--border);
  color: var(--text-2);
  font: 12px var(--font-mono);
  padding: 6px 8px;
}

.index-filter-bar {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(180px, 0.65fr);
  gap: 10px;
}

.index-filter-bar label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.index-filter-bar span {
  color: var(--text-3);
  font: 12px var(--font-mono);
}

.index-filter-bar input,
.index-filter-bar select {
  min-width: 0;
  min-height: 36px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-1);
  font-size: 13px;
  padding: 0 10px;
}

.index-dialog-actions button {
  min-height: 32px;
  padding: 6px 10px;
  border: 1px solid var(--border-strong);
  background: var(--surface-2);
  color: var(--acid);
  font: 700 12px var(--font-mono);
  cursor: pointer;
}

.manual-index-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 8px;
  min-width: 0;
}

.manual-index-grid button {
  display: grid;
  gap: 6px;
  min-width: 0;
  min-height: 138px;
  padding: 10px;
  border: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--text-1);
  text-align: left;
  cursor: pointer;
}

.manual-index-grid button.selected {
  border-color: var(--accent-strong);
  background: color-mix(in srgb, var(--accent) 9%, var(--surface-1));
}

.manual-index-grid button.disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.manual-index-code {
  color: var(--acid);
  font: 800 12px var(--font-mono);
}

.manual-index-grid strong,
.manual-index-grid small,
.manual-index-grid em {
  min-width: 0;
  overflow-wrap: anywhere;
}

.manual-index-grid strong {
  font-size: 13px;
}

.manual-index-grid small {
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.45;
}

.manual-index-grid em {
  color: var(--text-2);
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.manual-index-grid button.disabled em {
  color: var(--warning);
}

.submit-index-button {
  justify-self: end;
}

.band-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px;
}

.band-grid label {
  display: grid;
  gap: 5px;
}

.band-grid span {
  color: var(--text-3);
  font-size: 12px;
}

.band-grid select {
  min-width: 0;
  min-height: 32px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-1);
  font-size: 12px;
}

.source-band-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--border);
  background: var(--surface-1);
}

.source-band-list span {
  overflow: hidden;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.band-mapping-modal p {
  margin: 0;
  color: var(--warning);
  font-size: 12px;
  line-height: 1.5;
}

.save-mapping-button {
  justify-self: end;
  min-width: 88px;
}

.primary-action:disabled,
.batch-action:disabled,
.save-mapping-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

@media (max-width: 1500px) {
  .asset-toolbar {
    grid-template-columns: minmax(0, 1.4fr) repeat(2, minmax(170px, 0.7fr));
  }

  .batch-action {
    min-height: 68px;
  }
}

@media (max-width: 980px) {
  .asset-toolbar {
    grid-template-columns: 1fr 1fr;
  }

  .asset-import-card,
  .batch-action {
    grid-column: 1 / -1;
  }
}

@media (max-width: 620px) {
  .asset-toolbar {
    grid-template-columns: 1fr;
  }

  .band-grid {
    grid-template-columns: 1fr 1fr;
  }

  .source-band-list {
    grid-template-columns: 1fr;
  }

  .index-filter-bar {
    grid-template-columns: 1fr;
  }

  .asset-import-card {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .primary-action {
    grid-column: 1 / -1;
  }
}
</style>
