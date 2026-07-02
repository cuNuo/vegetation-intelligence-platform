
// frontend/src/types/platform.ts
// 文件说明：前后端共享的平台 API 响应类型与遥感业务数据结构。

export interface RasterMetadata {
  path: string
  width: number
  height: number
  count: number
  dtypes: string[]
  crs: string | null
  bounds: [number, number, number, number]
  geographicBounds: [number, number, number, number] | null
  resolution: [number, number]
  nodata: number | null
  descriptions: Array<string | null>
  sensor?: string | null
  bandInferenceSource?: 'filename-profile' | null
  overviewLevels?: number[]
  overviewCount?: number
  overviewStatus?: 'built' | 'reused' | 'not-needed'
  bandMetadata?: Array<{
    band: number
    description: string | null
    tags: Record<string, string>
    wavelengthNm: number | null
  }>
}

export interface UploadedAsset {
  objectKey: string
  localPath: string
  filename: string
  size: number
  metadata: RasterMetadata
  previewPath?: string | null
  previewObjectKey?: string | null
}

export interface IndexMetadata {
  id: string
  name: string
  formula: string
  requiredBands: string[]
  description: string
  expectedRange: [number, number] | null
  parameters: Record<string, number>
  categories: string[]
  recommendationTags: string[]
  limitations: string[]
}

export interface AgentRecommendation extends IndexMetadata {
  executable: boolean
  missingBands: string[]
  reason: string
}

export interface AgentTraceStep {
  id: string
  title: string
  status: 'done' | 'running' | 'warning' | 'blocked'
  detail?: string
}

export interface AgentKnowledgeHit {
  title: string
  content: string
  source: string
  score: number
}

export interface AgentKnowledgeDocument {
  id: string
  title: string
  content: string
  source: string
  sessionId?: string | null
  storage: 'postgresql' | 'memory'
}

export interface AgentConversationEvent {
  id: string
  role: 'user' | 'assistant' | 'system'
  eventType: 'question' | 'plan' | 'execution' | 'interpretation' | string
  content: string
  payload: Record<string, unknown>
  createdAt: string
}

export interface AgentLLMConfig {
  provider: 'openai-compatible' | 'anthropic'
  baseUrl: string
  token: string
  model: string
  temperature: number
}

export interface AgentCustomIndexDraft {
  id: string
  name: string
  expression: string
  description: string
}

export interface AgentPlan {
  id: string
  sessionId: string
  status: 'awaiting_confirmation' | 'confirmed'
  intent: string
  title: string
  summary: string
  recommendations: AgentRecommendation[]
  selectedIndices: string[]
  engine: 'numpy' | 'joblib' | 'torch'
  engineReason: string
  estimatedMemoryMb: number
  suggestedBlockSize: number
  warnings: string[]
  requiresConfirmation: boolean
  canExecute: boolean
  trace: AgentTraceStep[]
  processSteps: AgentTraceStep[]
  knowledgeHits: AgentKnowledgeHit[]
  webHits: AgentKnowledgeHit[]
  llmStatus: 'used' | 'skipped' | 'failed'
  llmProvider: string
  llmMessage: string
  customIndex?: IndexMetadata | null
  agentMode: string
  conversation: AgentConversationEvent[]
  jobId?: string
}

export interface AgentExecutionSheet {
  indices: string[]
  engine: 'auto' | 'numpy' | 'joblib' | 'torch'
  blockSize: number
  priority: number
}

export interface AgentInsight {
  title: string
  severity: 'normal' | 'warning' | 'danger'
  detail: string
}

export interface AgentResultInterpretation {
  summary: string
  insights: AgentInsight[]
  nextActions: string[]
  llmStatus: 'used' | 'skipped' | 'failed'
  llmMessage?: string
  trace: AgentTraceStep[]
  conversation?: AgentConversationEvent[]
}

export interface AgentStreamEvent {
  event: 'status' | 'plan' | 'job' | 'result' | 'done' | 'error' | string
  data: {
    message?: string
    plan?: AgentPlan
    job?: JobRecord
    [key: string]: unknown
  }
}

export interface JobRecord {
  id: string
  status: string
  progress: number
  message: string
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
  eta_seconds?: number | null
  throughput?: number | null
  current?: number
  total?: number
  engine?: string
  index_count?: number
  error: string | null
  result?: RasterResult
}

export interface Histogram {
  counts: number[]
  edges: number[]
}

export interface Product {
  index: string
  name: string
  path: string
  previewPath: string | null
  objectKey?: string | null
  previewObjectKey?: string | null
  bounds: [number, number, number, number]
  crs: string | null
  statistics: {
    validPixels: number
    minimum: number | null
    maximum: number | null
    mean: number | null
    median: number | null
    standardDeviation: number | null
    histogram: Histogram
  } | null
}

export interface RasterResult {
  actualEngine: string
  durationSeconds: number
  fallbackReasons: string[]
  products: Product[]
}

export interface SystemCapabilities {
  cuda: boolean
  engines: string[]
  indexCount: number
  totalIndexCount: number
  customIndexCount: number
  customIndexStorage: 'postgresql' | 'memory'
  agentSessionStorage: 'postgresql' | 'memory'
  agentKnowledgeStorage: 'postgresql' | 'memory'
  asyncJobs: boolean
  objectStorage: string
  agentMode: string
}
