// frontend/src/utils/agentInterpretation.ts
// 文件说明：Agent 判读结果运行期规整工具。
// 主要职责：把后端、LLM 或兼容接口返回的松散数据转成前端可安全渲染的结构。
// 对外入口：normalizeAgentInterpretation。
// 依赖边界：只处理纯数据，不访问 DOM、Pinia 或网络。

import type { AgentInsight, AgentResultInterpretation, AgentTraceStep } from '@/types/platform'

const VALID_SEVERITIES = new Set<AgentInsight['severity']>(['normal', 'warning', 'danger'])
const VALID_TRACE_STATUSES = new Set<AgentTraceStep['status']>(['done', 'running', 'warning', 'blocked'])

/** 把未知值规整为字符串列表，防止 Vue v-for 把字符串拆成单字渲染。 */
function normalizeStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean)
  }
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? [text] : []
  }
  return []
}

/** 规整模型洞察列表，丢弃缺少标题或详情的异常项。 */
function normalizeInsights(value: unknown): AgentInsight[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const raw = item as Record<string, unknown>
    const title = String(raw.title ?? '').trim()
    const detail = String(raw.detail ?? '').trim()
    if (!title || !detail) return []
    const severity = VALID_SEVERITIES.has(raw.severity as AgentInsight['severity'])
      ? raw.severity as AgentInsight['severity']
      : 'normal'
    return [{ title, detail, severity }]
  })
}

/** 规整 trace，避免非数组返回破坏组件遍历。 */
function normalizeTrace(value: unknown): AgentTraceStep[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item, index) => {
    if (!item || typeof item !== 'object') return []
    const raw = item as Record<string, unknown>
    const title = String(raw.title ?? '').trim()
    if (!title) return []
    const status = VALID_TRACE_STATUSES.has(raw.status as AgentTraceStep['status'])
      ? raw.status as AgentTraceStep['status']
      : 'done'
    return [{
      id: String(raw.id ?? `trace-${index}`),
      title,
      status,
      detail: typeof raw.detail === 'string' ? raw.detail : undefined,
    }]
  })
}

/** 把 Agent 判读结果规整为组件可安全渲染的结构。 */
export function normalizeAgentInterpretation(value: unknown): AgentResultInterpretation {
  const raw = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  const llmStatus = ['used', 'skipped', 'failed'].includes(String(raw.llmStatus))
    ? raw.llmStatus as AgentResultInterpretation['llmStatus']
    : 'skipped'
  return {
    summary: String(raw.summary ?? '').trim() || '暂无可判读的统计摘要。',
    insights: normalizeInsights(raw.insights),
    nextActions: normalizeStringList(raw.nextActions),
    llmStatus,
    llmMessage: typeof raw.llmMessage === 'string' ? raw.llmMessage : undefined,
    trace: normalizeTrace(raw.trace),
    conversation: Array.isArray(raw.conversation) ? raw.conversation as AgentResultInterpretation['conversation'] : undefined,
  }
}
