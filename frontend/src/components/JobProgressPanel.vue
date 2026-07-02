<!-- frontend/src/components/JobProgressPanel.vue -->
<!-- 文件说明：异步任务进度与结果面板。 -->
<!-- 主要职责：展示状态、耗时、吞吐、产品切换、下载和取消入口。 -->
<!-- 对外约定：jobs/result props 与 select/cancel 事件。 -->
<!-- 依赖边界：不直接轮询后端。 -->

<script setup lang="ts">
import type { JobRecord, Product, RasterResult } from '@/types/platform'

defineProps<{
  jobs: JobRecord[]
  activeResult: RasterResult | null
  activeProductIndex: number
}>()

const emit = defineEmits<{
  selectResult: [job: JobRecord]
  selectJobProduct: [job: JobRecord, index: number]
  selectProduct: [index: number]
  cancelJob: [job: JobRecord]
}>()

/** 把后端任务状态转换为中文显示文本。 */
function statusLabel(status: string) {
  return (
    {
      accepted: '排队',
      running: '运行',
      successful: '完成',
      failed: '失败',
      dismissed: '取消',
    }[status] ?? status
  )
}

/** 把秒数格式化为易读时长。 */
function formatDuration(seconds?: number | null) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '估算中'
  if (seconds < 1) return '<1s'
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return minutes > 0 ? `${minutes}m ${rest}s` : `${rest}s`
}

/** 处理 elapsedSeconds 对应的组件交互或数据转换逻辑。 */
function elapsedSeconds(job: JobRecord) {
  const start = new Date(job.started_at ?? job.created_at).getTime()
  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now()
  return Math.max(0, (end - start) / 1000)
}

/** 根据已完成比例和耗时估算剩余时间。 */
function estimatedEta(job: JobRecord) {
  if (job.eta_seconds !== null && job.eta_seconds !== undefined) return job.eta_seconds
  if (!['accepted', 'running'].includes(job.status) || job.progress <= 0) return null
  const elapsed = elapsedSeconds(job)
  return Math.max(0, elapsed * (100 - job.progress) / job.progress)
}

/** 根据窗口进度估算吞吐率。 */
function estimatedThroughput(job: JobRecord) {
  if (job.throughput !== null && job.throughput !== undefined) return `${job.throughput.toFixed(2)} 窗口/s`
  const current = job.current ?? 0
  const elapsed = elapsedSeconds(job)
  if (current > 0 && elapsed > 0) return `${(current / elapsed).toFixed(2)} 窗口/s`
  return '待采样'
}

/** 处理 productCount 对应的组件交互或数据转换逻辑。 */
function productCount(job: JobRecord) {
  return job.result?.products?.length ?? job.index_count ?? 0
}

/** 处理 isProductActive 对应的组件交互或数据转换逻辑。 */
function isProductActive(job: JobRecord, index: number, activeResult: RasterResult | null, activeProductIndex: number) {
  const product = job.result?.products?.[index]
  const activeProduct = activeResult?.products?.[activeProductIndex]
  return Boolean(product && activeProduct && product.path === activeProduct.path)
}

/** 生成产品文件的下载地址。 */
function productDownloadUrl(product: Product) {
  const key = product.objectKey?.replaceAll('\\', '/').replace(/^\/+/, '')
  if (key) return `/artifacts/${key}`
  const normalized = product.path?.replaceAll('\\', '/')
  const marker = '/data/'
  const position = normalized.toLowerCase().lastIndexOf(marker)
  return position >= 0 ? `/artifacts/${normalized.slice(position + marker.length)}` : ''
}

/** 处理 productDownloadName 对应的组件交互或数据转换逻辑。 */
function productDownloadName(product: Product) {
  return product.path.split(/[\\/]/).pop() ?? `${product.index.toUpperCase()}.tif`
}
</script>

<template>
  <section class="jobs-panel">
    <header>
      <div>
        <span>COMPUTE QUEUE</span>
        <h2>任务管理器</h2>
      </div>
      <strong>{{ jobs.length.toString().padStart(2, '0') }}</strong>
    </header>
    <div v-if="jobs.length" class="job-list">
      <article
        v-for="job in jobs.slice(0, 8)"
        :key="job.id"
        class="job-item"
      >
        <div class="job-row">
          <code>{{ job.id.slice(0, 8).toUpperCase() }}</code>
          <span :class="`status status-${job.status}`">{{ statusLabel(job.status) }}</span>
        </div>
        <div class="progress-track">
          <span :style="{ width: `${job.progress}%` }" />
        </div>
        <div class="job-meta">
          <span>{{ job.message }}</span>
          <strong>{{ job.progress.toFixed(0) }}%</strong>
        </div>
        <dl class="job-facts">
          <div>
            <dt>ETA</dt>
            <dd>{{ formatDuration(estimatedEta(job)) }}</dd>
          </div>
          <div>
            <dt>速率</dt>
            <dd>{{ estimatedThroughput(job) }}</dd>
          </div>
          <div>
            <dt>已用</dt>
            <dd>{{ formatDuration(elapsedSeconds(job)) }}</dd>
          </div>
          <div>
            <dt>引擎</dt>
            <dd>{{ (job.result?.actualEngine ?? job.engine ?? 'auto').toUpperCase() }}</dd>
          </div>
          <div>
            <dt>指数</dt>
            <dd>{{ productCount(job) || '待定' }}</dd>
          </div>
          <div>
            <dt>窗口</dt>
            <dd>{{ job.current ?? 0 }} / {{ job.total ?? 0 }}</dd>
          </div>
        </dl>
        <div class="job-actions">
          <button
            type="button"
            :disabled="job.status !== 'successful'"
            @click="emit('selectResult', job)"
          >
            打开结果
          </button>
          <button
            type="button"
            :disabled="!['accepted', 'running'].includes(job.status)"
            @click="emit('cancelJob', job)"
          >
            取消
          </button>
        </div>
        <div v-if="job.result?.products?.length" class="product-switcher" aria-label="任务结果指数">
          <div
            v-for="(product, index) in job.result.products"
            :key="`${job.id}-${product.index}`"
            class="product-action"
          >
            <button
              type="button"
              :class="{
                active: isProductActive(job, index, activeResult, activeProductIndex),
              }"
              @click="emit('selectJobProduct', job, index)"
            >
              {{ product.index.toUpperCase() }}
            </button>
            <a
              v-if="job.status === 'successful' && productDownloadUrl(product)"
              :href="productDownloadUrl(product)"
              :download="productDownloadName(product)"
            >
              导出TIF
            </a>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="jobs-empty">等待第一个计算任务进入队列</div>
  </section>
</template>

<style scoped>
.jobs-panel {
  min-width: 0;
  min-height: 290px;
  padding: 22px;
  border: 1px solid var(--border-strong);
  background: var(--surface-1);
}

.jobs-panel header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 17px;
}

.jobs-panel header span {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
}

.jobs-panel h2 {
  margin: 5px 0 0;
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 500;
}

.jobs-panel header strong {
  color: rgba(188, 255, 66, 0.2);
  font-family: var(--font-display);
  font-size: 54px;
  line-height: 0.8;
}

.job-list {
  display: grid;
  gap: 8px;
}

.job-item {
  padding: 10px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: inherit;
  text-align: left;
}

.job-row,
.job-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.job-row code {
  color: var(--text-2);
  font-size: 12px;
}

.status {
  padding: 3px 5px;
  font-size: 12px;
}

.status-running,
.status-accepted {
  color: var(--warning);
}

.status-successful {
  color: var(--acid);
}

.status-failed {
  color: var(--danger);
}

.progress-track {
  height: 2px;
  margin: 9px 0 7px;
  overflow: hidden;
  background: var(--surface-3);
}

.progress-track span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent-strong), var(--accent));
  transition: width 300ms ease;
}

.job-meta {
  color: var(--muted);
  font-size: 12px;
}

.job-meta strong {
  color: var(--text-1);
  font-family: var(--font-mono);
}

.job-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin: 9px 0 0;
}

.job-facts div {
  min-width: 0;
  padding: 6px;
  border: 1px solid var(--border);
  background: var(--surface-1);
}

.job-facts dt,
.job-facts dd {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-facts dt {
  color: var(--muted);
  font-size: 11px;
}

.job-facts dd {
  margin-top: 3px;
  color: var(--text-1);
  font-family: var(--font-mono);
  font-size: 11px;
}

.job-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.job-actions button {
  flex: 1;
  padding: 6px;
  border: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--text-2);
  font-size: 12px;
  cursor: pointer;
}

.product-switcher {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.product-action {
  display: inline-grid;
  grid-template-columns: auto auto;
  min-width: 0;
  border: 1px solid var(--border);
  background: var(--surface-1);
}

.product-switcher button,
.product-switcher a {
  min-height: 28px;
  padding: 4px 7px;
  border: 0;
  background: transparent;
  color: var(--text-2);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.4;
  text-decoration: none;
  cursor: pointer;
}

.product-switcher button.active {
  background: var(--surface-hover);
  color: var(--acid);
}

.product-switcher a {
  border-left: 1px solid var(--border);
  color: var(--acid);
}

.job-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.jobs-empty {
  display: grid;
  min-height: 150px;
  place-items: center;
  border: 1px dashed var(--border-strong);
  color: var(--muted);
  font-size: 13px;
}
</style>
