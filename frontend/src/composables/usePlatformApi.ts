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

async function uploadForm<T>(url: string, formData: FormData): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail ?? '上传失败')
  }
  return response.json() as Promise<T>
}

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

function parseSseFrame(frame: string): AgentStreamEvent | null {
  const event = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim()
  const data = frame.match(/^data:\s*(.+)$/m)?.[1]
  if (!event || !data) return null
  return {
    event,
    data: JSON.parse(data) as AgentStreamEvent['data'],
  }
}

export function usePlatformApi() {

  async function uploadAsset(file: File): Promise<UploadedAsset> {
    const formData = new FormData()
    formData.append('file', file)
    return uploadForm<UploadedAsset>('/api/assets/upload', formData)
  }

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

  async function listIndices(): Promise<IndexMetadata[]> {
    const response = await requestJson<{ items: IndexMetadata[] }>('/api/indices')
    return response.items
  }

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

  async function listJobs(): Promise<JobRecord[]> {
    const response = await requestJson<{ jobs: JobRecord[] }>('/jobs')
    return response.jobs
  }

  async function getJob(jobId: string): Promise<JobRecord> {
    return requestJson<JobRecord>(`/jobs/${jobId}`)
  }

  async function cancelJob(jobId: string): Promise<JobRecord> {
    return requestJson<JobRecord>(`/jobs/${jobId}`, {
      method: 'DELETE',
    })
  }

  async function getResults(jobId: string): Promise<RasterResult> {
    return requestJson<RasterResult>(`/jobs/${jobId}/results`)
  }

  async function interpretResults(
    products: Product[],
    userGoal: string,
    llm?: AgentLLMConfig | null,
    sessionId?: string | null,
  ): Promise<AgentResultInterpretation> {
    return requestJson<AgentResultInterpretation>('/api/agent/interpret-results', {
      method: 'POST',
      body: JSON.stringify({
        products,
        userGoal,
        sessionId,
        llm,
      }),
    })
  }

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
