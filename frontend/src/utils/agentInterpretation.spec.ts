// frontend/src/utils/agentInterpretation.spec.ts
// 文件说明：Agent 判读结果规整工具测试。
// 主要职责：验证接口形状漂移不会传入可破坏布局的数据。
// 对外入口：npm run test:unit。
// 依赖边界：纯函数测试，不挂载组件、不访问网络。

import { describe, expect, it } from 'vitest'
import { normalizeAgentInterpretation } from '@/utils/agentInterpretation'

describe('normalizeAgentInterpretation', () => {
  it('把字符串 nextActions 规整为单条建议列表', () => {
    const result = normalizeAgentInterpretation({
      summary: '模型摘要',
      insights: [],
      nextActions: '复核地块边界和原始影像',
      llmStatus: 'used',
      trace: [],
    })

    expect(result.nextActions).toEqual(['复核地块边界和原始影像'])
    expect(result.llmStatus).toBe('used')
  })

  it('丢弃非数组 insights 并修正非法 severity', () => {
    const result = normalizeAgentInterpretation({
      summary: '',
      insights: [
        { title: 'NDVI 均值 0.900', detail: '整体长势较好。', severity: 'unexpected' },
        { title: '缺少详情', severity: 'warning' },
      ],
      nextActions: null,
      llmStatus: 'other',
      trace: 'bad trace',
    })

    expect(result.summary).toBe('暂无可判读的统计摘要。')
    expect(result.insights).toEqual([
      { title: 'NDVI 均值 0.900', detail: '整体长势较好。', severity: 'normal' },
    ])
    expect(result.nextActions).toEqual([])
    expect(result.llmStatus).toBe('skipped')
    expect(result.trace).toEqual([])
  })
})
