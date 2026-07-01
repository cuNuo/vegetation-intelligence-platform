<script setup lang="ts">
import type { JobRecord } from '@/types/platform'

defineProps<{
  jobs: JobRecord[]
}>()

const emit = defineEmits<{
  selectResult: [job: JobRecord]
  cancelJob: [job: JobRecord]
}>()

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
</script>

<template>
  <section class="jobs-panel">
    <header>
      <div>
        <span>COMPUTE QUEUE</span>
        <h2>任务脉冲</h2>
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
        <div class="job-actions">
          <button
            type="button"
            :disabled="job.status !== 'successful'"
            @click="emit('selectResult', job)"
          >
            结果
          </button>
          <button
            type="button"
            :disabled="!['accepted', 'running'].includes(job.status)"
            @click="emit('cancelJob', job)"
          >
            取消
          </button>
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
