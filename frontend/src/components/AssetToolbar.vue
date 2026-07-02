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
const uploadingFileName = shallowRef('')
const currentUploadProgress = shallowRef(0)
const totalUploadProgress = shallowRef(0)
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
const batchIndices = computed(() => store.activePlan?.selectedIndices ?? ['ndvi'])
const pyramidLevels = computed(() => {
  const asset = selectedAsset.value
  if (!asset) return []
  const levels: string[] = []
  let width = asset.metadata.width
  let height = asset.metadata.height
  let level = 1
  while (width > 256 || height > 256) {
    width = Math.max(1, Math.ceil(width / 2))
    height = Math.max(1, Math.ceil(height / 2))
    levels.push(`L${level} ${width}×${height}`)
    level += 1
    if (levels.length >= 5) break
  }
  return levels
})

function openPicker() {
  fileInput.value?.click()
}

async function uploadFiles(files: FileList | File[]) {
  const geotiffs = Array.from(files).filter((file) => /\.tiff?$/i.test(file.name))
  if (!geotiffs.length) {
    message.value = '未发现.tif或.tiff影像文件'
    return
  }
  isUploading.value = true
  currentUploadProgress.value = 0
  totalUploadProgress.value = 0
  message.value = `正在上传 ${geotiffs.length} 个影像…`
  try {
    const uploaded: UploadedAsset[] = []
    for (const [index, file] of geotiffs.entries()) {
      uploadingFileName.value = file.name
      uploaded.push(await api.uploadAsset(file, (progress) => {
        currentUploadProgress.value = progress
        totalUploadProgress.value = Math.round(((index + progress / 100) / geotiffs.length) * 100)
        message.value = `正在上传 ${file.name}：${progress}%（${index + 1}/${geotiffs.length}）`
      }))
    }
    store.addUploadedAssets(uploaded)
    totalUploadProgress.value = 100
    message.value = `已导入 ${uploaded.length} 个影像，可执行批量处理`
  } catch (error) {
    message.value = error instanceof Error ? error.message : '影像上传失败'
  } finally {
    isUploading.value = false
    uploadingFileName.value = ''
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) void uploadFiles(input.files)
  input.value = ''
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  if (event.dataTransfer?.files) void uploadFiles(event.dataTransfer.files)
}

async function submitBatch() {
  if (!store.asset.queue.length) {
    message.value = '请先导入至少一个GeoTIFF影像'
    return
  }
  isSubmittingBatch.value = true
  message.value = `正在提交 ${store.asset.queue.length} 个批量任务…`
  try {
    for (const asset of store.asset.queue) {
      await api.executeAssetBatch(
        asset.localPath,
        batchIndices.value,
        store.asset.bandMapping,
        store.activePlan?.engine ?? 'auto',
      )
    }
    message.value = `已提交 ${store.asset.queue.length} 个异步任务，任务中心将自动刷新`
  } catch (error) {
    message.value = error instanceof Error ? error.message : '批量任务提交失败'
  } finally {
    isSubmittingBatch.value = false
  }
}

function updateBandMapping(logicalBand: string, event: Event) {
  const select = event.target as HTMLSelectElement
  store.setBandMapping(logicalBand, Number(select.value))
}

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
        <p>{{ message }}</p>
        <div v-if="isUploading || totalUploadProgress > 0" class="upload-progress">
          <span :style="{ width: `${totalUploadProgress}%` }" />
        </div>
        <small v-if="isUploading" class="upload-detail">
          {{ uploadingFileName }} / {{ currentUploadProgress }}%
        </small>
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
      <strong>{{ pyramidLevels.length ? pyramidLevels.join(' / ') : '等待影像' }}</strong>
      <small>计算结果输出COG概览层，导入阶段预估预览层级</small>
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
      @click="submitBatch"
    >
      {{ isSubmittingBatch ? '提交中…' : `批量处理 ${batchIndices.join(' + ').toUpperCase()}` }}
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
                ? hasWavelengthMetadata
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
  min-height: clamp(78px, 7dvh, 112px);
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
  padding: 12px 14px;
}

.thumbnail {
  position: relative;
  display: grid;
  width: clamp(46px, 3.6vw, 58px);
  height: clamp(46px, 3.6vw, 58px);
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
.asset-stat small,
.upload-detail {
  display: block;
  margin: 5px 0 0;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.45;
}

.upload-progress {
  height: 5px;
  margin-top: 8px;
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
  padding: 12px 14px;
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
.batch-action:disabled {
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

  .asset-import-card {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .primary-action {
    grid-column: 1 / -1;
  }
}
</style>
