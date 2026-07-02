// frontend/src/components/AgentDrawer.spec.ts
// 文件说明：AgentDrawer 组件回归测试。
// 主要职责：固定 Agent 判读结果在异常接口形状下的渲染边界。
// 对外入口：npm run test:unit。
// 依赖边界：只挂载组件并模拟 Platform API，不访问真实后端。

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentDrawer from '@/components/AgentDrawer.vue'
import { useWorkspaceStore } from '@/stores/workspace'
import type { AgentPlan, AgentResultInterpretation, Product } from '@/types/platform'

const apiMock = vi.hoisted(() => ({
  createPlanStream: vi.fn(),
  confirmPlanStream: vi.fn(),
  getJob: vi.fn(),
  getResults: vi.fn(),
  importAgentKnowledge: vi.fn(),
  interpretResults: vi.fn(),
}))

vi.mock('@/composables/usePlatformApi', () => ({
  usePlatformApi: () => apiMock,
}))

const productFixture: Product = {
  index: 'ndvi',
  name: '归一化植被指数',
  path: 'output/ndvi.tif',
  previewPath: null,
  bounds: [0, 0, 1, 1],
  crs: 'EPSG:4326',
  statistics: {
    validPixels: 100,
    minimum: 0.08,
    maximum: 0.95,
    mean: 0.9,
    median: 0.91,
    standardDeviation: 0.04,
    histogram: {
      counts: [1, 99],
      edges: [0, 0.5, 1],
    },
  },
}

const planFixture: AgentPlan = {
  id: 'b38c80-plan',
  sessionId: 'd7f255d1',
  status: 'awaiting_confirmation',
  intent: '水分胁迫判读',
  title: '植被水分胁迫辅助分析',
  summary: '结合植被活力和短波红外水分响应识别潜在胁迫。',
  recommendations: [
    {
      id: 'ndvi',
      name: '归一化植被指数',
      formula: '(nir - red) / (nir + red)',
      requiredBands: ['nir', 'red'],
      description: '判读植被活力。',
      expectedRange: [-1, 1],
      parameters: {},
      categories: ['vegetation'],
      recommendationTags: ['growth'],
      limitations: [],
      executable: true,
      missingBands: [],
      reason: '适合验证植被健康趋势。',
    },
  ],
  selectedIndices: ['ndvi'],
  engine: 'numpy',
  engineReason: '测试默认引擎',
  estimatedMemoryMb: 12,
  suggestedBlockSize: 1024,
  warnings: [],
  requiresConfirmation: true,
  canExecute: true,
  trace: [],
  processSteps: [],
  knowledgeHits: [],
  webHits: [],
  llmStatus: 'skipped',
  llmProvider: 'rules',
  llmMessage: '规则兜底',
  customIndex: null,
  agentMode: 'rules',
  conversation: [],
}

function mountAgentDrawer() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useWorkspaceStore()
  store.setActivePlan(planFixture)
  store.setActiveResult({
    actualEngine: 'numpy',
    durationSeconds: 1,
    fallbackReasons: [],
    products: [productFixture],
  })
  const wrapper = mount(AgentDrawer, {
    global: {
      plugins: [pinia],
    },
  })
  return { wrapper, store }
}

function malformedInterpretation(value: unknown): AgentResultInterpretation {
  return value as AgentResultInterpretation
}

describe('AgentDrawer 判读结果渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('把字符串 nextActions 渲染为一条完整建议，避免逐字撑开判读卡', async () => {
    const { wrapper } = mountAgentDrawer()
    apiMock.interpretResults.mockResolvedValueOnce(
      malformedInterpretation({
        summary: 'NDVI 分析显示该区域植被覆盖状况良好。',
        insights: [
          {
            title: 'NDVI 均值 0.900',
            severity: 'normal',
            detail: '整体长势较好，可关注局部低值斑块是否集中。',
          },
        ],
        nextActions: '把 NDMI、MSI、近期降雨和灌溉记录放在同一地块边界内复核。',
        llmStatus: 'used',
        trace: [],
      }),
    )

    await wrapper.find('.secondary-button').trigger('click')
    await flushPromises()

    const actions = wrapper.findAll('.next-actions p')
    expect(actions).toHaveLength(1)
    expect(actions[0].text()).toBe('把 NDMI、MSI、近期降雨和灌溉记录放在同一地块边界内复核。')
    expect(wrapper.find('.insight-card-header > span').text()).toBe('模型增强')
  })

  it('忽略非数组 insights，避免异常接口返回破坏执行单与判读卡布局', async () => {
    const { wrapper } = mountAgentDrawer()
    apiMock.interpretResults.mockResolvedValueOnce(
      malformedInterpretation({
        summary: '模型只返回了摘要。',
        insights: '外部模型误把 insights 返回成字符串',
        nextActions: [],
        llmStatus: 'skipped',
        trace: [],
      }),
    )

    await wrapper.find('.secondary-button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.insight-card').exists()).toBe(true)
    expect(wrapper.findAll('.insight-row')).toHaveLength(0)
    expect(wrapper.find('.next-actions').exists()).toBe(false)
  })
})
