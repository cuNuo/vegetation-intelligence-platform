<!-- frontend/src/components/AgentDrawer.vue -->
<!-- 文件说明：智能体对话、方案确认、知识导入和结果解读侧栏。 -->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, shallowRef, useTemplateRef, watch } from 'vue'
import { usePlatformApi } from '@/composables/usePlatformApi'
import { useWorkspaceStore } from '@/stores/workspace'
import type {
  AgentConversationEvent,
  AgentExecutionSheet,
  AgentLLMConfig,
  AgentTraceStep,
  AgentResultInterpretation,
  AgentStreamEvent,
  AgentKnowledgeHit,
} from '@/types/platform'

interface AgentThinkingStep {
  id: string
  title: string
  detail: string
  status: AgentTraceStep['status']
}

interface QueuedThinkingStep extends AgentThinkingStep {
  finalStatus: AgentTraceStep['status']
}

const store = useWorkspaceStore()
const api = usePlatformApi()
const prompt = shallowRef('')
const lastUserGoal = shallowRef('')
const isThinking = shallowRef(false)
const isInterpreting = shallowRef(false)
const isConfigOpen = shallowRef(false)
const isKnowledgeOpen = shallowRef(false)
const isDetailsOpen = shallowRef(false)
const isKnowledgeImporting = shallowRef(false)
const errorMessage = shallowRef('')
const knowledgeMessage = shallowRef('')
const enableWebSearch = shallowRef(true)
const customIndexEnabled = shallowRef(false)
const interpretation = shallowRef<AgentResultInterpretation | null>(null)
const observedJobId = shallowRef('')
const executionMessage = shallowRef('')
const thinkingSteps = shallowRef<AgentThinkingStep[]>([])
const thinkingQueue: QueuedThinkingStep[] = []
const thinkingFinalizeTimers: number[] = []
let thinkingQueueTimer: number | null = null
const FIRST_THINKING_DELAY_MS = 420
const THINKING_STEP_DELAY_MS = 1180
const THINKING_MIN_DWELL_MS = 760
const llmConfig = reactive<AgentLLMConfig>({
  provider: 'openai-compatible',
  baseUrl: '',
  token: '',
  model: 'gpt-4.1-mini',
  temperature: 0,
})
const customIndex = reactive({
  id: 'custom_nd',
  name: '自定义归一化差异指数',
  expression: '(nir - red) / (nir + red)',
  description: '用于演示运行期新增指数，表达式会先经过安全校验。',
})
const executionSheet = reactive<AgentExecutionSheet>({
  indices: [],
  engine: 'auto',
  blockSize: 1024,
  priority: 3,
})
const timelineRef = useTemplateRef<HTMLElement>('timeline')
const knowledgeDraft = reactive({
  title: '植被指数适用场景说明',
  content: '',
  source: 'agent-upload',
})
const localConversation = shallowRef<AgentConversationEvent[]>([])

const executableCount = computed(
  () => store.activePlan?.recommendations.filter((item) => item.executable).length ?? 0,
)
const executableRecommendations = computed(() =>
  store.activePlan?.recommendations.filter((entry) => entry.executable) ?? [],
)
const visibleSources = computed(() => dedupeSources([
  ...(store.activePlan?.knowledgeHits ?? []),
  ...(store.activePlan?.webHits ?? []),
]))
const visibleThinkingSteps = computed(() => {
  const merged = thinkingSteps.value
  const byKey = new Map<string, AgentTraceStep>()
  for (const step of merged) {
    const key = thinkingStepKey(step.title, step.detail)
    byKey.set(key, step)
  }
  return Array.from(byKey.values()).slice(-5)
})
const visibleTraceSteps = computed(() => {
  const steps = store.activePlan?.trace ?? []
  const byKey = new Map<string, AgentTraceStep>()
  for (const step of steps) {
    const key = thinkingStepKey(step.title, step.detail ?? '')
    byKey.set(key, step)
  }
  return Array.from(byKey.values())
})
const interpretationProducts = computed(() => {
  if (store.activeProduct) return [store.activeProduct]
  const completed = store.completedJobs.find((job) => job.result?.products?.length)
  return completed?.result?.products ?? []
})
const canUseLlm = computed(() => llmConfig.baseUrl.length > 0 && llmConfig.token.length > 0)
const activeJob = computed(() =>
  store.activePlan?.jobId ? store.jobs.find((job) => job.id === store.activePlan?.jobId) : null,
)
const conversationEvents = computed<AgentConversationEvent[]>(() => {
  const persisted = interpretation.value?.conversation?.length
    ? interpretation.value.conversation
    : store.activePlan?.conversation ?? []
  const localOnly = localConversation.value.filter(
    (local) =>
      !persisted.some(
        (event) =>
          event.role === local.role &&
          event.eventType === local.eventType &&
          event.content === local.content,
      ),
  )
  return [...localOnly, ...persisted].sort(
    (left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime(),
  )
})
const statusLine = computed(() => {
  if (isThinking.value) return '正在检索指数库、网络资料和可执行工具'
  if (isInterpreting.value) return '正在读取统计信息并生成建议'
  if (executionMessage.value) return executionMessage.value
  if (store.activePlan?.status === 'awaiting_confirmation') return '方案已生成，等待人工确认'
  return '待命'
})

function currentLlmConfig(): AgentLLMConfig | null {
  if (!canUseLlm.value) return null
  return { ...llmConfig }
}

function eventTitle(event: AgentConversationEvent): string {
  const labels: Record<string, string> = {
    question: '用户问题',
    plan: '方案生成',
    execution: '任务执行',
    interpretation: '统计解读',
  }
  return labels[event.eventType] ?? event.eventType
}

function syncConversation(events?: AgentConversationEvent[]) {
  if (!events?.length || !store.activePlan) return
  store.activePlan.conversation = events
}

function appendLocalMessage(role: AgentConversationEvent['role'], content: string, eventType = 'question') {
  const id = `${Date.now()}-${localConversation.value.length}`
  localConversation.value = [
    ...localConversation.value,
    {
      id,
      role,
      eventType,
      content,
      payload: {},
      createdAt: new Date().toISOString(),
    },
  ]
  void scrollConversationToLatest()
  return id
}

async function scrollConversationToLatest() {
  await nextTick()
  const element = timelineRef.value
  if (element) element.scrollTop = element.scrollHeight
}

function appendStatus(content: string, eventType = 'execution') {
  appendLocalMessage('system', content, eventType)
}

function dedupeSources(sources: AgentKnowledgeHit[]) {
  const seen = new Set<string>()
  return sources.filter((source) => {
    const key = `${source.title}|${source.source}|${source.content}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function appendThinkingStep(title: string, detail: string, status: AgentTraceStep['status'] = 'running') {
  const key = thinkingStepKey(title, detail)
  const existing = thinkingSteps.value.findIndex((step) => thinkingStepKey(step.title, step.detail) === key)
  const step = {
    id: `${Date.now()}-${thinkingSteps.value.length}`,
    title,
    detail,
    status,
  }
  thinkingSteps.value = existing >= 0
    ? thinkingSteps.value.map((item, index) => (index === existing ? { ...item, status } : item))
    : [...thinkingSteps.value, step].slice(-8)
}

function enqueueThinkingStep(title: string, detail: string, status: AgentTraceStep['status'] = 'running') {
  const revealStatus = status === 'done' ? 'running' : status
  thinkingQueue.push({
    id: `${Date.now()}-${thinkingQueue.length}`,
    title,
    detail,
    status: revealStatus,
    finalStatus: status,
  })
  scheduleThinkingQueue()
}

function scheduleThinkingQueue() {
  if (thinkingQueueTimer !== null) return
  const delay = thinkingSteps.value.length ? THINKING_STEP_DELAY_MS : FIRST_THINKING_DELAY_MS
  thinkingQueueTimer = window.setTimeout(flushThinkingQueue, delay)
}

function flushThinkingQueue() {
  thinkingQueueTimer = null
  const next = thinkingQueue.shift()
  if (!next) return
  appendThinkingStep(next.title, next.detail, next.status)
  if (next.finalStatus !== next.status) {
    const timer = window.setTimeout(() => {
      appendThinkingStep(next.title, next.detail, next.finalStatus)
    }, THINKING_MIN_DWELL_MS)
    thinkingFinalizeTimers.push(timer)
  }
  if (thinkingQueue.length) scheduleThinkingQueue()
}

function resetThinkingStream() {
  thinkingSteps.value = []
  thinkingQueue.splice(0)
  while (thinkingFinalizeTimers.length) {
    const timer = thinkingFinalizeTimers.pop()
    if (timer !== undefined) window.clearTimeout(timer)
  }
  if (thinkingQueueTimer !== null) {
    window.clearTimeout(thinkingQueueTimer)
    thinkingQueueTimer = null
  }
}

function thinkingStepKey(title: string, detail: string) {
  return `${title.trim()}|${detail.replace(/\s+/g, ' ').trim()}`
}

function extractErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function handlePlanStreamEvent(event: AgentStreamEvent) {
  if (event.event === 'thought') {
    enqueueThinkingStep(
      typeof event.data.title === 'string' ? event.data.title : '思考过程',
      typeof event.data.detail === 'string' ? event.data.detail : '',
      ['done', 'running', 'warning', 'blocked'].includes(String(event.data.status))
        ? event.data.status as AgentTraceStep['status']
        : 'running',
    )
    return
  }
  if (event.event === 'status' || event.event === 'done') {
    const message = typeof event.data.message === 'string' ? event.data.message : '智能体状态已更新'
    enqueueThinkingStep(event.event === 'done' ? '完成' : '状态更新', message, event.event === 'done' ? 'done' : 'running')
    return
  }
  if (event.event === 'plan') {
    const plan = event.data as unknown as NonNullable<typeof store.activePlan>
    store.setActivePlan(plan)
    resetExecutionSheet()
    isDetailsOpen.value = false
    if (!plan.conversation.length) appendLocalMessage('assistant', plan.summary, 'plan')
    return
  }
  if (event.event === 'error') {
    const message = typeof event.data.message === 'string' ? event.data.message : '方案生成失败'
    errorMessage.value = message
    appendStatus(`方案生成失败：${message}`, 'plan')
  }
}

async function handleConfirmStreamEvent(event: AgentStreamEvent) {
  if (event.event === 'status' || event.event === 'done') {
    const message = typeof event.data.message === 'string' ? event.data.message : '任务状态已更新'
    executionMessage.value = message
    return
  }
  if (event.event === 'plan') {
    const plan = event.data as unknown as NonNullable<typeof store.activePlan>
    store.setActivePlan(plan)
    syncConversation(plan.conversation)
    return
  }
  if (event.event === 'job') {
    const job = event.data as unknown as NonNullable<typeof activeJob.value>
    const merged = [job, ...store.jobs.filter((item) => item.id !== job.id)]
    store.setJobs(merged)
    executionMessage.value = `${job.status} / ${job.progress}% / ${job.message}`
    return
  }
  if (event.event === 'result') {
    const result = event.data as unknown as NonNullable<NonNullable<typeof activeJob.value>['result']>
    if (!result?.products?.length) return
    const jobId = store.activePlan?.jobId
    if (jobId) {
      store.setJobs(
        store.jobs.map((job) => (job.id === jobId ? { ...job, result } : job)),
      )
    }
    store.setActiveResult(result)
    interpretation.value = await api.interpretResults(
      result.products,
      lastUserGoal.value,
      currentLlmConfig(),
      store.activePlan?.sessionId,
    )
    syncConversation(interpretation.value.conversation)
    executionMessage.value = '任务完成，已基于统计信息生成建议。'
    appendStatus(executionMessage.value, 'interpretation')
    return
  }
  if (event.event === 'error') {
    const message = typeof event.data.message === 'string' ? event.data.message : '任务执行失败'
    errorMessage.value = message
    executionMessage.value = `任务失败：${message}`
    appendStatus(executionMessage.value)
  }
}

function resetExecutionSheet() {
  if (!store.activePlan) return
  executionSheet.indices = [...store.activePlan.selectedIndices]
  executionSheet.engine = store.activePlan.engine
  executionSheet.blockSize = store.activePlan.suggestedBlockSize
  executionSheet.priority = 3
}

function toggleExecutionIndex(indexId: string) {
  if (executionSheet.indices.includes(indexId)) {
    executionSheet.indices = executionSheet.indices.filter((item) => item !== indexId)
    return
  }
  executionSheet.indices = [...executionSheet.indices, indexId]
}

async function importKnowledge() {
  if (!knowledgeDraft.content.trim()) {
    errorMessage.value = '请先输入或上传指数说明文档内容'
    return
  }
  isKnowledgeImporting.value = true
  errorMessage.value = ''
  try {
    const document = await api.importAgentKnowledge(
      knowledgeDraft.title,
      knowledgeDraft.content,
      knowledgeDraft.source,
      store.activePlan?.sessionId,
    )
    knowledgeMessage.value = `已导入 ${document.title}，存储模式 ${document.storage}，下次生成方案会进入RAG。`
    knowledgeDraft.content = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '知识导入失败'
  } finally {
    isKnowledgeImporting.value = false
  }
}

async function readKnowledgeFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  knowledgeDraft.title = file.name.replace(/\.[^.]+$/, '') || knowledgeDraft.title
  knowledgeDraft.source = `file:${file.name}`
  knowledgeDraft.content = await file.text()
  input.value = ''
}

async function generatePlan() {
  const message = prompt.value.trim()
  if (!message) return
  lastUserGoal.value = message
  // 先把用户输入推进本地对话流，避免等待后端期间界面没有“消息已发送”的反馈。
  appendLocalMessage('user', message)
  isThinking.value = true
  errorMessage.value = ''
  interpretation.value = null
  resetThinkingStream()
  try {
    await api.createPlanStream(message, store.asset.availableBands, {
      llm: currentLlmConfig(),
      enableWebSearch: enableWebSearch.value,
      customIndex: customIndexEnabled.value ? { ...customIndex } : null,
      sessionId: store.activePlan?.sessionId,
      rasterWidth: store.asset.selected?.metadata.width,
      rasterHeight: store.asset.selected?.metadata.height,
    }, handlePlanStreamEvent)
    prompt.value = ''
  } catch (error) {
    errorMessage.value = extractErrorMessage(error, '方案生成失败')
    appendStatus(`方案生成失败：${errorMessage.value}`, 'plan')
  } finally {
    isThinking.value = false
  }
}

async function confirmPlan() {
  if (!store.activePlan || !store.asset.localPath) {
    errorMessage.value = '请先通过上方按钮或拖拽导入GeoTIFF影像'
    return
  }
  if (!store.asset.availableBands.length) {
    errorMessage.value = '当前影像没有可用逻辑波段，请先导入有效GeoTIFF'
    appendStatus(errorMessage.value)
    return
  }
  if (!store.bandValidation.valid) {
    errorMessage.value = `波段映射未通过验证：${store.bandValidation.messages.join('；')}`
    appendStatus(errorMessage.value)
    return
  }
  isThinking.value = true
  errorMessage.value = ''
  try {
    await api.confirmPlanStream(
      store.activePlan.id,
      store.asset.localPath,
      store.asset.bandMapping,
      { ...executionSheet },
      handleConfirmStreamEvent,
    )
  } catch (error) {
    errorMessage.value = extractErrorMessage(error, '任务提交失败')
    appendStatus(`任务提交失败：${errorMessage.value}`)
  } finally {
    isThinking.value = false
  }
}

watch(
  () => store.activePlan?.id,
  () => resetExecutionSheet(),
)

watch(
  () => conversationEvents.value.length,
  () => {
    void scrollConversationToLatest()
  },
)

watch(
  observedJobId,
  (jobId, _previous, onCleanup) => {
    if (!jobId) return
    let stopped = false
    const timer = window.setInterval(async () => {
      if (stopped) return
      try {
        const job = await api.getJob(jobId)
        const merged = [job, ...store.jobs.filter((item) => item.id !== job.id)]
        store.setJobs(merged)
        executionMessage.value = `${job.status} / ${job.progress}% / ${job.message}`
        if (job.status === 'successful' || job.status === 'failed') {
          stopped = true
          window.clearInterval(timer)
          if (job.status === 'successful') {
            const result = await api.getResults(jobId)
            store.setJobs([{ ...job, result }, ...merged.filter((item) => item.id !== job.id)])
            store.setActiveResult(result)
            interpretation.value = await api.interpretResults(
              result.products,
              lastUserGoal.value,
              currentLlmConfig(),
              store.activePlan?.sessionId,
            )
            syncConversation(interpretation.value.conversation)
            executionMessage.value = '任务完成，已基于统计信息生成建议。'
          }
        }
      } catch (error) {
        executionMessage.value = error instanceof Error ? error.message : '任务状态轮询失败'
      }
    }, 1500)
    onCleanup(() => {
      stopped = true
      window.clearInterval(timer)
    })
  },
)

onBeforeUnmount(() => {
  resetThinkingStream()
})

async function interpretResults() {
  if (!interpretationProducts.value.length) {
    errorMessage.value = '请先完成一次指数计算，或在结果面板中选中一个产品'
    return
  }
  isInterpreting.value = true
  errorMessage.value = ''
  try {
    interpretation.value = await api.interpretResults(
      interpretationProducts.value,
      lastUserGoal.value,
      currentLlmConfig(),
      store.activePlan?.sessionId,
    )
    syncConversation(interpretation.value.conversation)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '统计解读失败'
  } finally {
    isInterpreting.value = false
  }
}
</script>

<template>
  <aside class="agent-panel">
    <header class="agent-header">
      <div>
        <span class="eyebrow">AGRONOMY COPILOT</span>
        <h2>对话</h2>
        <div class="agent-header-status">
          <span>{{ statusLine }}</span>
          <span>{{ canUseLlm ? `${llmConfig.provider} / ${llmConfig.model}` : '规则引擎兜底' }}</span>
          <span>{{ enableWebSearch ? '网络检索开启' : '仅本地RAG' }}</span>
          <span>{{ store.activePlan?.sessionId ? `SESSION ${store.activePlan.sessionId.slice(0, 8)}` : 'NEW SESSION' }}</span>
        </div>
      </div>
      <div class="header-actions">
        <button class="config-button" type="button" @click="isKnowledgeOpen = true">知识库</button>
        <button class="config-button" type="button" @click="isConfigOpen = true">
          {{ canUseLlm ? '模型' : '配置' }}
        </button>
      </div>
    </header>

    <div class="agent-scroll">
      <section class="conversation">
        <div v-if="!conversationEvents.length" class="agent-message">
          <span>AI</span>
          <p>输入你的判读目标，我会生成可确认的计算方案。</p>
        </div>
        <div v-if="conversationEvents.length" ref="timeline" class="message-timeline">
          <article
            v-for="event in conversationEvents"
            :key="event.id"
            :class="['timeline-message', event.role]"
          >
            <span>{{ event.role === 'user' ? 'YOU' : event.role === 'system' ? 'RUN' : 'AI' }}</span>
            <div>
              <strong>{{ eventTitle(event) }}</strong>
              <p>{{ event.content }}</p>
            </div>
          </article>
        </div>
      </section>

      <section v-if="visibleThinkingSteps.length" class="thinking-panel">
        <div class="section-title compact">
          <span>思考过程</span>
          <small>{{ isThinking ? 'streaming' : `${visibleThinkingSteps.length} steps` }}</small>
        </div>
        <article
          v-for="step in visibleThinkingSteps"
          :key="step.id"
          :class="['thinking-step', step.status]"
        >
          <span />
          <div>
            <strong>{{ step.title }}</strong>
            <small>{{ step.detail }}</small>
          </div>
        </article>
      </section>

    <section v-if="store.activePlan" class="plan-card">
      <div class="plan-heading">
        <div>
          <div class="plan-number">PLAN / {{ store.activePlan.id.slice(0, 6).toUpperCase() }}</div>
          <h3>{{ store.activePlan.title }}</h3>
        </div>
        <button class="details-toggle" type="button" @click="isDetailsOpen = !isDetailsOpen">
          {{ isDetailsOpen ? '收起详情' : '展开详情' }}
        </button>
      </div>
      <p>{{ store.activePlan.summary }}</p>
      <div class="agent-mode">
        <span>{{ store.activePlan.agentMode }}</span>
        <span>{{ store.activePlan.llmProvider }} / {{ store.activePlan.llmStatus }}</span>
      </div>
      <p class="llm-message">{{ store.activePlan.llmMessage }}</p>
      <div class="plan-metrics">
        <div>
          <span>可执行指数</span>
          <strong>{{ executableCount }}</strong>
        </div>
        <div>
          <span>推荐引擎</span>
          <strong>{{ store.activePlan.engine.toUpperCase() }}</strong>
        </div>
        <div>
          <span>估算内存</span>
          <strong>{{ store.activePlan.estimatedMemoryMb }} MB</strong>
        </div>
      </div>

      <div class="execution-sheet primary-execution">
        <div class="section-title compact">
          <span>执行指数</span>
          <small>{{ executionSheet.indices.length }} / {{ executableRecommendations.length }}</small>
        </div>
        <div class="execution-indices">
          <label
            v-for="item in executableRecommendations"
            :key="item.id"
          >
            <input
              type="checkbox"
              :checked="executionSheet.indices.includes(item.id)"
              @change="toggleExecutionIndex(item.id)"
            />
            <span>{{ item.id.toUpperCase() }}</span>
            <small>{{ item.name }}</small>
          </label>
        </div>
        <div class="execution-controls">
          <label>
            <span>引擎</span>
            <select v-model="executionSheet.engine">
              <option value="auto">Auto</option>
              <option value="numpy">NumPy</option>
              <option value="joblib">Joblib</option>
              <option value="torch">Torch</option>
            </select>
          </label>
          <label>
            <span>Block Size</span>
            <input v-model.number="executionSheet.blockSize" type="number" min="128" max="2048" step="128" />
          </label>
          <label>
            <span>优先级</span>
            <input v-model.number="executionSheet.priority" type="number" min="1" max="5" step="1" />
          </label>
        </div>
      </div>

      <button
        class="confirm-button"
        :disabled="
          !store.activePlan.canExecute ||
          !store.asset.localPath ||
          !executionSheet.indices.length ||
          isThinking ||
          store.activePlan.status === 'confirmed'
        "
        @click="confirmPlan"
      >
        {{
          store.activePlan.status === 'confirmed'
            ? `任务已提交 ${store.activePlan.jobId}`
            : !store.asset.localPath
              ? '请先导入影像'
              : '确认并提交计算'
        }}
      </button>
      <div v-if="store.activePlan.jobId" class="job-status-card">
        <div class="section-title compact">
          <span>执行状态</span>
          <small>{{ activeJob?.status ?? 'submitted' }}</small>
        </div>
        <div class="progress-track">
          <span :style="{ width: `${activeJob?.progress ?? 4}%` }"></span>
        </div>
        <p>{{ executionMessage || '等待任务队列返回状态。' }}</p>
      </div>
      <button
        class="secondary-button"
        :disabled="isInterpreting || !interpretationProducts.length"
        @click="interpretResults"
      >
        {{ isInterpreting ? '正在解读统计…' : '根据统计生成建议' }}
      </button>

      <template v-if="isDetailsOpen">

      <label class="switch-row custom-toggle">
        <input v-model="customIndexEnabled" type="checkbox" />
        同时新建自定义指数
      </label>
      <div v-if="customIndexEnabled" class="custom-index-box">
        <input v-model="customIndex.id" aria-label="自定义指数ID" placeholder="指数ID，如 nd_custom" />
        <input v-model="customIndex.name" aria-label="自定义指数名称" placeholder="指数名称" />
        <textarea v-model="customIndex.expression" rows="2" aria-label="自定义指数表达式" />
        <input v-model="customIndex.description" aria-label="自定义指数说明" placeholder="适用场景说明" />
      </div>

      <details class="trace-list">
        <summary>
          <span>运行过程</span>
          <small>{{ visibleTraceSteps.length }} steps</small>
        </summary>
        <article v-for="step in visibleTraceSteps" :key="step.id" :class="['trace-item', step.status]">
          <span class="trace-dot"></span>
          <div>
            <strong>{{ step.title }}</strong>
            <small>{{ step.detail }}</small>
          </div>
        </article>
      </details>

      <div class="recommendations">
        <article
          v-for="item in store.activePlan.recommendations"
          :key="item.id"
          :class="{ blocked: !item.executable }"
        >
          <div class="index-badge">{{ item.id.toUpperCase() }}</div>
          <div>
            <strong>{{ item.name }}</strong>
            <small>{{ item.reason }}</small>
            <em v-if="item.missingBands.length">
              缺少 {{ item.missingBands.join(' / ') }}
            </em>
          </div>
        </article>
      </div>

      <details v-if="visibleSources.length" class="source-list">
        <summary>
          <span>检索来源</span>
          <small>{{ visibleSources.length }} 条，已去重</small>
        </summary>
        <article v-for="source in visibleSources.slice(0, 3)" :key="`${source.source}-${source.title}-${source.content}`">
          <strong>{{ source.title }}</strong>
          <small>{{ source.source }}</small>
          <p>{{ source.content }}</p>
        </article>
      </details>

      <div v-if="store.activePlan.warnings.length" class="warning-box">
        <span>质量提示</span>
        <p v-for="warning in store.activePlan.warnings" :key="warning">{{ warning }}</p>
      </div>

      </template>
    </section>

    <section v-if="interpretation" class="insight-card">
      <div class="plan-number">RESULT ADVICE</div>
      <h3>统计判读意见</h3>
      <p>{{ interpretation.summary }}</p>
      <article
        v-for="insight in interpretation.insights"
        :key="insight.title"
        :class="['insight-row', insight.severity]"
      >
        <strong>{{ insight.title }}</strong>
        <small>{{ insight.detail }}</small>
      </article>
      <div class="next-actions">
        <span>下一步</span>
        <p v-for="action in interpretation.nextActions" :key="action">{{ action }}</p>
      </div>
    </section>

    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    </div>

    <div class="prompt-box">
      <textarea
        v-model="prompt"
        rows="3"
        aria-label="分析需求"
        placeholder="输入判读目标，例如：找出长势异常区域并解释原因"
        @keydown.ctrl.enter.prevent="generatePlan"
      />
      <button :disabled="isThinking || prompt.length < 2" @click="generatePlan">
        {{ isThinking ? '生成中…' : '发送' }}
      </button>
    </div>

    <div v-if="isKnowledgeOpen" class="modal-backdrop" @click.self="isKnowledgeOpen = false">
      <section class="config-modal" role="dialog" aria-modal="true" aria-label="外部知识库">
        <header class="modal-header">
          <div>
            <span class="eyebrow">KNOWLEDGE BASE</span>
            <h3>外部知识库</h3>
          </div>
          <button type="button" class="icon-button" @click="isKnowledgeOpen = false">×</button>
        </header>
        <div class="knowledge-import modal-knowledge">
          <input v-model="knowledgeDraft.title" aria-label="知识标题" placeholder="文档标题" />
          <textarea
            v-model="knowledgeDraft.content"
            rows="8"
            aria-label="指数说明文档内容"
            placeholder="粘贴指数适用场景、限制、判读经验；或选择 .txt/.md 文件。"
          />
          <div class="knowledge-actions">
            <label>
              导入文件
              <input type="file" accept=".txt,.md,.csv" @change="readKnowledgeFile" />
            </label>
            <button type="button" :disabled="isKnowledgeImporting" @click="importKnowledge">
              {{ isKnowledgeImporting ? '导入中…' : '写入RAG' }}
            </button>
          </div>
          <p v-if="knowledgeMessage">{{ knowledgeMessage }}</p>
        </div>
      </section>
    </div>

    <div v-if="isConfigOpen" class="modal-backdrop" @click.self="isConfigOpen = false">
      <section class="config-modal" role="dialog" aria-modal="true" aria-label="智能体模型配置">
        <header class="modal-header">
          <div>
            <span class="eyebrow">AGENT SETTINGS</span>
            <h3>模型与检索配置</h3>
          </div>
          <button type="button" class="icon-button" @click="isConfigOpen = false">×</button>
        </header>
        <label class="switch-row modal-switch">
          <input v-model="enableWebSearch" type="checkbox" />
          联合网络检索
        </label>
        <div class="config-grid">
          <label>
            <span>格式</span>
            <select v-model="llmConfig.provider">
              <option value="openai-compatible">OpenAI兼容</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </label>
          <label>
            <span>模型</span>
            <input v-model="llmConfig.model" placeholder="gpt-4.1-mini / claude-sonnet-4" />
          </label>
        </div>
        <label class="field-stack">
          <span>BASE URL</span>
          <input v-model="llmConfig.baseUrl" placeholder="https://api.example.com/v1" />
        </label>
        <label class="field-stack">
          <span>TOKEN</span>
          <input v-model="llmConfig.token" type="password" placeholder="仅本次请求使用，不写入仓库" />
        </label>
        <button type="button" class="confirm-button modal-save" @click="isConfigOpen = false">
          保存本次配置
        </button>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.agent-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
  height: 100%;
  min-height: 0;
  padding: 22px;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  background:
    linear-gradient(180deg, var(--surface-2), var(--surface-1)),
    radial-gradient(
      circle at 80% 0%,
      color-mix(in srgb, var(--accent) 12%, transparent),
      transparent 40%
    );
}

.agent-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border);
}

.agent-scroll {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow: auto;
  padding-right: 3px;
  isolation: isolate;
}

.eyebrow,
.plan-number {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.16em;
}

.agent-header h2 {
  margin: 6px 0 0;
  font-family: var(--font-display);
  font-size: 23px;
  font-weight: 500;
}

.agent-header-status {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 8px;
  color: var(--muted-light);
  font-size: 12px;
  line-height: 1.4;
}

.agent-header-status span {
  position: relative;
}

.agent-header-status span + span::before {
  position: absolute;
  left: -8px;
  color: var(--border-strong);
  content: "/";
}

.config-button {
  min-width: 54px;
  padding: 6px 8px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 800;
  white-space: nowrap;
  word-break: keep-all;
  cursor: pointer;
}

.header-actions {
  display: flex;
  flex-shrink: 0;
  gap: 7px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-1);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 800;
}

.section-title.compact {
  margin: 12px 0 8px;
  color: var(--acid);
}

.section-title small {
  color: var(--muted);
  font-size: 9px;
}

.switch-row {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--muted-light);
  font-size: 10px;
}

.switch-row input {
  accent-color: var(--acid);
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}

.config-grid label,
.field-stack {
  display: grid;
  gap: 5px;
}

.config-grid span,
.field-stack span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 8px;
}

.config-grid input,
.config-grid select,
.field-stack input,
.custom-index-box input,
.custom-index-box textarea {
  min-width: 0;
  width: 100%;
  padding: 9px;
  border: 1px solid var(--border);
  outline: 0;
  background: var(--surface-0);
  color: var(--text-1);
  font: 11px/1.4 var(--font-body);
}

.field-stack {
  margin-top: 9px;
}

.conversation {
  display: grid;
  min-height: 0;
  gap: 12px;
  padding: 14px 0 0;
}

.agent-message {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 10px;
  color: var(--muted-light);
  font-size: 12px;
  line-height: 1.7;
}

.agent-message span {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 50%;
  background: var(--acid);
  color: var(--surface-0);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 800;
}

.agent-message p {
  margin: 0;
}

.message-timeline {
  display: grid;
  min-height: 96px;
  gap: 8px;
  align-content: end;
  margin-top: 0;
  padding: 2px 3px 8px 0;
}

.thinking-panel {
  display: grid;
  gap: 6px;
  max-height: min(240px, 30dvh);
  min-height: 0;
  overflow: auto;
  padding: 9px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface-hover) 72%, transparent);
  contain: layout paint;
  position: relative;
  z-index: 1;
}

.thinking-panel .section-title.compact {
  margin: 0 0 8px;
}

.thinking-step {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  min-width: 0;
}

.thinking-step > span {
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 12px color-mix(in srgb, var(--accent) 38%, transparent);
}

.thinking-step.running > span {
  animation: thinking-pulse 1.2s ease-in-out infinite;
}

.thinking-step.done > span {
  background: var(--acid);
}

.thinking-step.warning > span {
  background: var(--warning);
}

.thinking-step strong,
.thinking-step small {
  display: block;
  overflow-wrap: anywhere;
}

.thinking-step strong {
  color: var(--text-1);
  font-size: 12px;
}

.thinking-step.running strong::after {
  margin-left: 6px;
  color: var(--accent-strong);
  content: "进行中";
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 800;
}

.thinking-step small {
  margin-top: 2px;
  color: var(--muted-light);
  font-size: 12px;
  line-height: 1.45;
}

.timeline-message {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: 9px;
}

.timeline-message > span {
  display: grid;
  height: 24px;
  place-items: center;
  border: 1px solid var(--border-strong);
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 8px;
  font-weight: 800;
}

.timeline-message.user > span {
  color: var(--text-1);
}

.timeline-message > div {
  min-width: 0;
  padding: 8px 9px;
  border: 1px solid var(--border);
  background: var(--surface-0);
}

.timeline-message strong,
.timeline-message p {
  display: block;
  overflow-wrap: anywhere;
}

.timeline-message strong {
  color: var(--text-1);
  font-size: 10px;
}

.timeline-message p {
  margin: 4px 0 0;
  color: var(--muted-light);
  font-size: 10px;
  line-height: 1.5;
}

.custom-toggle {
  margin-top: 14px;
}

.custom-index-box {
  display: grid;
  gap: 7px;
  margin-top: 10px;
  padding: 10px;
  border: 1px solid var(--border);
  background: var(--surface-hover);
}

.knowledge-import {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding: 10px;
  border: 1px solid var(--border);
  background: var(--surface-hover);
}

.knowledge-import input,
.knowledge-import textarea,
.execution-controls input,
.execution-controls select {
  min-width: 0;
  width: 100%;
  padding: 8px;
  border: 1px solid var(--border);
  outline: 0;
  background: var(--surface-0);
  color: var(--text-1);
  font: 10px/1.4 var(--font-body);
}

.knowledge-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.knowledge-actions label,
.knowledge-actions button {
  display: grid;
  min-height: 34px;
  place-items: center;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 800;
  cursor: pointer;
}

.knowledge-actions input {
  display: none;
}

.knowledge-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.knowledge-import p {
  margin: 0;
  color: var(--muted-light);
  font-size: 9px;
  line-height: 1.5;
}

.prompt-box {
  margin-top: 0;
  border: 1px solid var(--border-strong);
  background: var(--surface-0);
  box-shadow: 0 -14px 30px color-mix(in srgb, var(--surface-1) 88%, transparent);
}

.prompt-box textarea {
  width: 100%;
  padding: 14px;
  border: 0;
  outline: 0;
  resize: vertical;
  background: transparent;
  color: var(--text-1);
  font: 13px/1.6 var(--font-body);
}

.prompt-box button,
.confirm-button,
.secondary-button {
  width: 100%;
  padding: 12px;
  border: 0;
  background: var(--acid);
  color: var(--surface-0);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  cursor: pointer;
}

.prompt-box button:disabled,
.confirm-button:disabled,
.secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.details-toggle {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  background: var(--surface-2);
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
  cursor: pointer;
}

.secondary-button {
  margin-top: 8px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--acid);
}

.job-status-card {
  margin-top: 10px;
  padding: 10px;
  border: 1px solid var(--border);
  background: var(--surface-hover);
}

.progress-track {
  height: 7px;
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--surface-0);
}

.progress-track span {
  display: block;
  height: 100%;
  background: var(--acid);
  transition: width 180ms ease;
}

.job-status-card p {
  margin: 8px 0 0;
  color: var(--muted-light);
  font-size: 9px;
  line-height: 1.5;
}

.plan-card {
  position: relative;
  z-index: 0;
  min-height: 0;
  margin: 8px 0 2px;
  padding: 16px 14px;
  border: 1px solid var(--border-strong);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-hover) 56%, transparent), transparent 46%),
    var(--surface-1);
}

.plan-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.plan-heading > div {
  min-width: 0;
}

.plan-card h3 {
  margin: 7px 0;
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.plan-card > p {
  color: var(--muted-light);
  font-size: 11px;
  line-height: 1.6;
}

.agent-mode {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.agent-mode span {
  padding: 5px 7px;
  border: 1px solid var(--border);
  color: var(--muted-light);
  font-family: var(--font-mono);
  font-size: 8px;
}

.llm-message {
  margin-top: 8px;
}

.plan-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin: 14px -14px 0;
  border-block: 1px solid var(--border);
}

.plan-metrics div {
  padding: 12px 7px;
}

.plan-metrics div + div {
  border-left: 1px solid var(--border);
}

.plan-metrics span,
.plan-metrics strong {
  display: block;
}

.plan-metrics span {
  color: var(--muted);
  font-size: 9px;
}

.plan-metrics strong {
  margin-top: 5px;
  color: var(--text-1);
  font-family: var(--font-mono);
  font-size: 11px;
}

.recommendations {
  display: grid;
  gap: 7px;
}

.trace-list {
  margin-bottom: 14px;
}

.trace-list summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 34px;
  padding: 8px 10px;
  border: 1px solid var(--border-strong);
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
  cursor: pointer;
}

.trace-list summary small {
  color: var(--muted);
  font-size: 12px;
}

.trace-item {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.trace-dot {
  width: 9px;
  height: 9px;
  margin-top: 4px;
  border-radius: 999px;
  background: var(--acid);
}

.trace-item.warning .trace-dot {
  background: var(--warning);
}

.trace-item strong,
.trace-item small {
  display: block;
}

.trace-item strong {
  font-size: 10px;
}

.trace-item small {
  margin-top: 3px;
  color: var(--muted);
  font-size: 9px;
  line-height: 1.5;
}

.recommendations article {
  display: grid;
  grid-template-columns: 62px 1fr;
  gap: 11px;
  padding: 10px;
  border: 1px solid var(--border);
  background: var(--surface-hover);
}

.recommendations article.blocked {
  opacity: 0.45;
}

.index-badge {
  display: grid;
  place-items: center;
  border: 1px solid var(--border-strong);
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 10px;
}

.recommendations strong,
.recommendations small,
.recommendations em {
  display: block;
}

.recommendations strong {
  font-size: 11px;
}

.recommendations small {
  margin-top: 3px;
  color: var(--muted);
  font-size: 9px;
}

.recommendations em {
  margin-top: 4px;
  color: var(--warning);
  font-size: 9px;
  font-style: normal;
}

.source-list {
  margin-top: 14px;
}

.source-list summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 34px;
  padding: 8px 10px;
  border: 1px solid var(--border-strong);
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
  cursor: pointer;
}

.source-list summary small {
  color: var(--muted);
  font-size: 12px;
}

.source-list article {
  padding: 9px;
  border: 1px solid var(--border);
  background: var(--surface-0);
}

.source-list article + article {
  margin-top: 7px;
}

.source-list strong,
.source-list small {
  display: block;
}

.source-list strong {
  font-size: 10px;
}

.source-list small {
  margin-top: 3px;
  overflow-wrap: anywhere;
  color: var(--acid);
  font-size: 8px;
}

.source-list p {
  margin: 5px 0 0;
  color: var(--muted-light);
  font-size: 9px;
  line-height: 1.5;
}

.warning-box {
  margin: 14px 0;
  padding: 8px 10px;
  border-left: 2px solid #dca35c;
  background: color-mix(in srgb, var(--warning) 9%, transparent);
}

.warning-box span {
  color: var(--warning);
  font-size: 9px;
  font-weight: 700;
}

.warning-box p {
  margin: 4px 0 0;
  color: var(--text-2);
  font-size: 9px;
  line-height: 1.45;
}

.execution-sheet {
  margin: 14px -4px 0;
  padding: 10px;
  border: 1px solid var(--border-strong);
  background: var(--surface-0);
}

.primary-execution {
  margin-top: 12px;
}

.execution-indices {
  display: grid;
  gap: 7px;
}

.execution-indices label {
  display: grid;
  grid-template-columns: 18px 48px 1fr;
  gap: 7px;
  align-items: center;
  min-height: 30px;
  padding: 7px;
  border: 1px solid var(--border);
  color: var(--muted-light);
  font-size: 9px;
}

.execution-indices input {
  accent-color: var(--acid);
}

.execution-indices span {
  color: var(--acid);
  font-family: var(--font-mono);
  font-weight: 800;
}

.execution-indices small {
  overflow-wrap: anywhere;
}

.execution-controls {
  display: grid;
  grid-template-columns: 1fr 1fr 0.8fr;
  gap: 8px;
  margin-top: 10px;
}

.execution-controls label {
  display: grid;
  gap: 5px;
}

.execution-controls span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 8px;
}

.error-message {
  color: var(--danger);
  font-size: 11px;
}

.insight-card {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.insight-card h3 {
  margin: 7px 0;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 500;
}

.insight-card > p {
  color: var(--muted-light);
  font-size: 11px;
  line-height: 1.6;
}

.insight-row {
  margin-top: 8px;
  padding: 9px;
  border-left: 2px solid var(--acid);
  background: var(--surface-hover);
}

.insight-row.warning {
  border-left-color: var(--warning);
}

.insight-row.danger {
  border-left-color: var(--danger);
}

.insight-row strong,
.insight-row small {
  display: block;
}

.insight-row strong {
  font-size: 10px;
}

.insight-row small,
.next-actions p {
  margin-top: 5px;
  color: var(--muted-light);
  font-size: 9px;
  line-height: 1.5;
}

.next-actions {
  margin-top: 12px;
}

.next-actions span {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 800;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgb(0 0 0 / 36%);
}

.config-modal {
  width: min(560px, 100%);
  max-height: min(720px, calc(100vh - 36px));
  padding: 22px;
  overflow: auto;
  border: 1px solid var(--border-strong);
  background: var(--surface-1);
  box-shadow: 0 24px 80px rgb(0 0 0 / 24%);
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  margin: 6px 0 0;
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 500;
}

.icon-button {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-1);
  font-size: 20px;
  cursor: pointer;
}

.modal-switch {
  margin: 16px 0 4px;
  align-items: flex-start;
  line-height: 1.5;
}

.modal-save {
  margin-top: 16px;
}

.modal-knowledge {
  margin-top: 16px;
}

.agent-panel {
  font-size: 14px;
}

.eyebrow,
.plan-number,
.section-title small,
.timeline-message > span,
.config-grid span,
.field-stack span,
.execution-controls span,
.next-actions span {
  font-size: 12px;
  letter-spacing: 0;
}

.config-button,
.section-title,
.switch-row,
.knowledge-actions label,
.knowledge-actions button,
.prompt-box button,
.confirm-button,
.secondary-button,
.timeline-message strong,
.trace-item strong,
.recommendations strong,
.source-list strong,
.insight-row strong {
  font-size: 13px;
}

.agent-message,
.timeline-message p,
.knowledge-import p,
.plan-card > p,
.trace-item small,
.recommendations small,
.recommendations em,
.source-list small,
.source-list p,
.warning-box span,
.warning-box p,
.execution-indices label,
.error-message,
.insight-card > p,
.insight-row small,
.next-actions p {
  font-size: 12px;
}

.config-grid input,
.config-grid select,
.field-stack input,
.custom-index-box input,
.custom-index-box textarea,
.knowledge-import input,
.knowledge-import textarea,
.execution-controls input,
.execution-controls select,
.prompt-box textarea {
  font-size: 13px;
}

@media (max-width: 1100px) {
  .agent-panel {
    height: auto;
    min-height: 420px;
    max-height: none;
  }

  .execution-controls {
    grid-template-columns: 1fr;
  }
}

@keyframes thinking-pulse {
  50% {
    opacity: 0.35;
    transform: scale(1.45);
  }
}
</style>
