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
const message = shallowRef('选择或拖入GeoTIFF，系统会保存到后端输入目录')

const mappedBandCount = computed(
  () => Object.values(store.asset.bandMapping).filter((band) => band > 0).length,
)
const selectedAsset = computed(() => store.asset.selected)
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
  message.value = `正在上传 ${geotiffs.length} 个影像…`
  try {
    const uploaded: UploadedAsset[] = []
    for (const file of geotiffs) {
      uploaded.push(await api.uploadAsset(file))
    }
    store.addUploadedAssets(uploaded)
    message.value = `已导入 ${uploaded.length} 个影像，可执行批量处理`
  } catch (error) {
    message.value = error instanceof Error ? error.message : '影像上传失败'
  } finally {
    isUploading.value = false
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

    <div class="asset-stat">
      <span>逻辑波段</span>
      <strong>{{ mappedBandCount }} / 7 已映射</strong>
      <small>{{ selectedAsset ? `${selectedAsset.metadata.count} 个源波段` : '默认多光谱映射' }}</small>
    </div>

    <button
      class="batch-action"
      :disabled="isSubmittingBatch || isUploading || !store.asset.queue.length"
      @click="submitBatch"
    >
      {{ isSubmittingBatch ? '提交中…' : `批量处理 ${batchIndices.join(' + ').toUpperCase()}` }}
    </button>
  </section>
</template>

<style scoped>
.asset-toolbar {
  display: grid;
  grid-template-columns: minmax(min(100%, 460px), 1.45fr) repeat(3, minmax(min(100%, 180px), 0.7fr)) minmax(min(100%, 180px), 0.5fr);
  gap: 1px;
  min-width: 0;
  min-height: clamp(78px, 7dvh, 112px);
  overflow: hidden;
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
.asset-stat small {
  display: block;
  margin: 5px 0 0;
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.45;
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

  .asset-import-card {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .primary-action {
    grid-column: 1 / -1;
  }
}
</style>
