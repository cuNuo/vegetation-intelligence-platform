import type {
  AgentPlan,
  AgentExecutionSheet,
  AgentKnowledgeDocument,
  AgentLLMConfig,
  AgentResultInterpretation,
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
    confirmPlan,
    importAgentKnowledge,
    listJobs,
    getJob,
    cancelJob,
    getResults,
    interpretResults,
    getCapabilities,
  }
}
