// frontend/src/composables/usePlatformApi.ts
// 文件说明：平台 HTTP 与 SSE 客户端。
// 主要职责：统一请求、错误解析、上传进度、流式事件和业务接口封装。
// 对外入口：usePlatformApi。
// 依赖边界：组件不得重复实现同类 fetch/SSE 解析。

import type {
  AgentPlan,
  AgentExecutionSheet,
  AgentKnowledgeDocument,
  AgentLLMConfig,
  AgentResultInterpretation,
  AgentStreamEvent,
  IndexMetadata,
  JobRecord,
  Product,
  RasterResult,
  SystemCapabilities,
  UploadedAsset,
} from '@/types/platform'
import { normalizeAgentInterpretation } from '@/utils/agentInterpretation'

/** 发送 JSON 请求，统一检查 HTTP 状态并解析结构化错误。 */
async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail ?? '请求失败')
  }
  return response.json() as Promise<T>
}

/** 使用 XMLHttpRequest 上传文件，以便实时上报字节级进度。 */
async function uploadForm<T>(
  url: string,
  formData: FormData,
  onProgress?: (progress: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      const payload = parseUploadResponse<T>(xhr.responseText)
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100)
        resolve(payload)
        return
      }
      reject(new Error(payload.detail ?? '上传失败'))
    }
    xhr.onerror = () => reject(new Error('上传连接失败'))
    xhr.send(formData)
  })
}

/** 解析上传响应，并在非 JSON 返回时生成可读错误。 */
function parseUploadResponse<T>(responseText: string): T & { detail?: string } {
  try {
    return JSON.parse(responseText || '{}') as T & { detail?: string }
  } catch {
    return { detail: responseText || '上传失败' } as T & { detail?: string }
  }
}

/** 消费 fetch ReadableStream，按 SSE 帧持续分发事件。 */
async function requestStream(
  url: string,
  body: unknown,
  onEvent: (event: AgentStreamEvent) => void | Promise<void>,
): Promise<void> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail ?? '流式请求失败')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const parsed = parseSseFrame(frame)
      if (parsed) await onEvent(parsed)
    }
  }
  const tail = parseSseFrame(buffer)
  if (tail) await onEvent(tail)
}

/** 解析单个 SSE 帧的 event/data 字段并忽略不完整数据。 */
function parseSseFrame(frame: string): AgentStreamEvent | null {
  const event = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim()
  const data = frame.match(/^data:\s*(.+)$/m)?.[1]
  if (!event || !data) return null
  return {
    event,
    data: JSON.parse(data) as AgentStreamEvent['data'],
  }
}

/** 返回平台所有 REST、上传和 SSE 调用方法。 */
export function usePlatformApi() {

  /** 处理 uploadAsset 对应的组件交互或数据转换逻辑。 */
  async function uploadAsset(
    file: File,
    onProgress?: (progress: number) => void,
  ): Promise<UploadedAsset> {
    const formData = new FormData()
    formData.append('file', file)
    return uploadForm<UploadedAsset>('/api/assets/upload', formData, onProgress)
  }

  /** 处理 executeAssetBatch 对应的组件交互或数据转换逻辑。 */
  async function executeAssetBatch(
    localPath: string,
    indices: string[],
    bands: Record<string, number>,
    engine = 'auto',
  ): Promise<{ jobID: string; status: string; location: string }> {
    return requestJson<{ jobID: string; status: string; location: string }>(
      '/processes/batch/execution',
      {
        method: 'POST',
        headers: { Prefer: 'respond-async' },
        body: JSON.stringify({
          source: { localPath },
          indices,
          bands,
          engine,
          blockSize: 1024,
          priority: 3,
          statistics: true,
          preview: true,
        }),
      },
    )
  }

  /** 处理 listIndices 对应的组件交互或数据转换逻辑。 */
  async function listIndices(): Promise<IndexMetadata[]> {
    const response = await requestJson<{ items: IndexMetadata[] }>('/api/indices')
    return response.items
  }

  /** 处理 createPlan 对应的组件交互或数据转换逻辑。 */
  async function createPlan(
    message: string,
    availableBands: string[],
    options: {
      llm?: AgentLLMConfig | null
      enableWebSearch?: boolean
      customIndex?: {
        id: string
        name: string
        expression: string
        description: string
      } | null
      sessionId?: string | null
    } = {},
  ): Promise<AgentPlan> {
    return requestJson<AgentPlan>('/api/agent/plan', {
      method: 'POST',
      body: JSON.stringify({
        message,
        sessionId: options.sessionId,
        availableBands,
        llm: options.llm,
        enableWebSearch: options.enableWebSearch ?? true,
        customIndex: options.customIndex,
      }),
    })
  }

  /** 处理 createPlanStream 对应的组件交互或数据转换逻辑。 */
  async function createPlanStream(
    message: string,
    availableBands: string[],
    options: {
      llm?: AgentLLMConfig | null
      enableWebSearch?: boolean
      customIndex?: {
        id: string
        name: string
        expression: string
        description: string
      } | null
      sessionId?: string | null
      rasterWidth?: number | null
      rasterHeight?: number | null
    },
    onEvent: (event: AgentStreamEvent) => void | Promise<void>,
  ): Promise<void> {
    return requestStream(
      '/api/agent/plan/stream',
      {
        message,
        sessionId: options.sessionId,
        availableBands,
        rasterWidth: options.rasterWidth,
        rasterHeight: options.rasterHeight,
        llm: options.llm,
        enableWebSearch: options.enableWebSearch ?? true,
        customIndex: options.customIndex,
      },
      onEvent,
    )
  }

  /** 提交人工确认后的执行单并流式跟踪任务。 */
  async function confirmPlan(
    planId: string,
    localPath: string,
    bands: Record<string, number>,
    executionSheet: AgentExecutionSheet,
  ): Promise<AgentPlan> {
    return requestJson<AgentPlan>(`/api/agent/plans/${planId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({
        source: { localPath },
        bands,
        indices: executionSheet.indices,
        engine: executionSheet.engine,
        blockSize: executionSheet.blockSize,
        priority: executionSheet.priority,
      }),
    })
  }

  /** 处理 confirmPlanStream 对应的组件交互或数据转换逻辑。 */
  async function confirmPlanStream(
    planId: string,
    localPath: string,
    bands: Record<string, number>,
    executionSheet: AgentExecutionSheet,
    onEvent: (event: AgentStreamEvent) => void | Promise<void>,
  ): Promise<void> {
    return requestStream(
      `/api/agent/plans/${planId}/confirm/stream`,
      {
        source: { localPath },
        bands,
        indices: executionSheet.indices,
        engine: executionSheet.engine,
        blockSize: executionSheet.blockSize,
        priority: executionSheet.priority,
      },
      onEvent,
    )
  }

  /** 处理 importAgentKnowledge 对应的组件交互或数据转换逻辑。 */
  async function importAgentKnowledge(
    title: string,
    content: string,
    source: string,
    sessionId?: string | null,
  ): Promise<AgentKnowledgeDocument> {
    return requestJson<AgentKnowledgeDocument>('/api/agent/knowledge', {
      method: 'POST',
      body: JSON.stringify({
        title,
        content,
        source,
        sessionId,
      }),
    })
  }

  /** 处理 listJobs 对应的组件交互或数据转换逻辑。 */
  async function listJobs(): Promise<JobRecord[]> {
    const response = await requestJson<{ jobs: JobRecord[] }>('/jobs')
    return response.jobs
  }

  /** 处理 getJob 对应的组件交互或数据转换逻辑。 */
  async function getJob(jobId: string): Promise<JobRecord> {
    return requestJson<JobRecord>(`/jobs/${jobId}`)
  }

  /** 请求取消任务并立即刷新任务列表。 */
  async function cancelJob(jobId: string): Promise<JobRecord> {
    return requestJson<JobRecord>(`/jobs/${jobId}`, {
      method: 'DELETE',
    })
  }

  /** 处理 getResults 对应的组件交互或数据转换逻辑。 */
  async function getResults(jobId: string): Promise<RasterResult> {
    return requestJson<RasterResult>(`/jobs/${jobId}/results`)
  }

  /** 请求 Agent 根据当前产品统计生成解释。 */
  async function interpretResults(
    products: Product[],
    userGoal: string,
    llm?: AgentLLMConfig | null,
    sessionId?: string | null,
  ): Promise<AgentResultInterpretation> {
    const payload = await requestJson<unknown>('/api/agent/interpret-results', {
      method: 'POST',
      body: JSON.stringify({
        products,
        userGoal,
        sessionId,
        llm,
      }),
    })
    return normalizeAgentInterpretation(payload)
  }

  /** 处理 getCapabilities 对应的组件交互或数据转换逻辑。 */
  async function getCapabilities(): Promise<SystemCapabilities> {
    return requestJson<SystemCapabilities>('/api/system/capabilities')
  }

  return {
    uploadAsset,
    executeAssetBatch,
    listIndices,
    createPlan,
    createPlanStream,
    confirmPlan,
    confirmPlanStream,
    importAgentKnowledge,
    listJobs,
    getJob,
    cancelJob,
    getResults,
    interpretResults,
    getCapabilities,
  }
}
