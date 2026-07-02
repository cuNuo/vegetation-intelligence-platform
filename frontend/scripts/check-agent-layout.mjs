// frontend/scripts/check-agent-layout.mjs
// 文件说明：Agent 侧栏真实浏览器布局回归检查。
// 主要职责：挂载真实 AgentDrawer，注入异常判读响应，并检测关键卡片是否发生几何重叠。
// 对外入口：npm run test:layout:agent。
// 依赖边界：只访问本地 Vite 开发服务，不访问真实后端。

import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const BASE_URL = process.env.AGENT_LAYOUT_URL ?? 'http://127.0.0.1:5174'
const SCREENSHOT_PATH = '../output/playwright/agent-drawer-layout-regression.png'

function overlaps(left, right) {
  return !(
    left.right <= right.left
    || right.right <= left.left
    || left.bottom <= right.top
    || right.bottom <= left.top
  )
}

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 303, height: 943 } })
  await page.route('**/api/agent/interpret-results', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        summary: 'NDVI分析显示该区域植被被健康状况良好。平均NDVI值为0.897，标准差为0.0396，表明植被覆盖均匀且茂盛。直方图显示大部分像素NDVI值集中在高值区域。',
        insights: [
          {
            title: 'NDVI 均值 0.897',
            severity: 'normal',
            detail: '整体长势较好，可关注局部低值斑块是否集中。有效值范围0.088到0.954。标准差0.040，空间差异可控。',
          },
        ],
        nextActions: '把 NDMI、MSI、近期降雨、灌溉记录和土壤水分传感器放在同一地块边界内复核。',
        llmStatus: 'used',
        trace: [],
      }),
    })
  })

  await page.goto(BASE_URL, { waitUntil: 'networkidle' })
  await page.evaluate(async () => {
    document.body.innerHTML = '<div id="visual-root"></div>'
    const style = document.createElement('style')
    style.textContent = `
      html, body, #visual-root {
        width: 303px;
        height: 943px;
        margin: 0;
        overflow: hidden;
        background: var(--surface-0);
      }
      #visual-root {
        display: grid;
      }
    `
    document.head.append(style)

    const [{ createApp }, { createPinia, setActivePinia }, agentModule, storeModule] = await Promise.all([
      import('/node_modules/.vite/deps/vue.js'),
      import('/node_modules/.vite/deps/pinia.js'),
      import('/src/components/AgentDrawer.vue'),
      import('/src/stores/workspace.ts'),
    ])
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = storeModule.useWorkspaceStore(pinia)
    store.asset.localPath = 'input/example.tif'
    store.asset.selected = {
      objectKey: 'input/example.tif',
      localPath: 'input/example.tif',
      filename: 'example.tif',
      size: 1024,
      metadata: {
        path: 'input/example.tif',
        width: 256,
        height: 256,
        count: 4,
        dtypes: ['uint16'],
        crs: 'EPSG:4326',
        bounds: [0, 0, 1, 1],
        geographicBounds: [0, 0, 1, 1],
        resolution: [1, 1],
        nodata: null,
        descriptions: [],
      },
    }
    store.setActivePlan({
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
        {
          id: 'ndmi',
          name: '归一化水分指数',
          formula: '(nir - swir1) / (nir + swir1)',
          requiredBands: ['nir', 'swir1'],
          description: '判读冠层水分。',
          expectedRange: [-1, 1],
          parameters: {},
          categories: ['water'],
          recommendationTags: ['water'],
          limitations: [],
          executable: true,
          missingBands: [],
          reason: '辅助识别水分胁迫。',
        },
        {
          id: 'msi',
          name: '水分胁迫指数',
          formula: 'swir1 / nir',
          requiredBands: ['swir1', 'nir'],
          description: '识别水分胁迫。',
          expectedRange: [0, 2],
          parameters: {},
          categories: ['water'],
          recommendationTags: ['water'],
          limitations: [],
          executable: true,
          missingBands: [],
          reason: '辅助识别水分胁迫。',
        },
      ],
      selectedIndices: ['ndvi', 'ndmi', 'msi'],
      engine: 'numpy',
      engineReason: '测试默认引擎',
      estimatedMemoryMb: 169.17,
      suggestedBlockSize: 1024,
      warnings: [
        '定期监控NDVI变化以跟踪植被健康趋势和季节性变化。',
        '结合其他遥感指标如NDMI、MSI及LAI，增强植被指数EVI或气象数据，进行多源数据融合分析。',
        '规划实地验证调查，采样NDVI异常区域，并结合土壤和作物记录定位问题。',
      ],
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
      conversation: [
        {
          id: 'conversation-1',
          role: 'assistant',
          eventType: 'plan',
          content: 'NDVI分析显示该区域植被被健康状况良好。平均NDVI值为0.90，标准差为0.0396，表明植被覆盖均匀且茂盛。直方图显示大部分像素NDVI值集中在高值区域。',
          payload: {},
          createdAt: new Date().toISOString(),
        },
      ],
    })
    store.setActiveResult({
      actualEngine: 'numpy',
      durationSeconds: 1,
      fallbackReasons: [],
      products: [
        {
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
            histogram: { counts: [1, 99], edges: [0, 0.5, 1] },
          },
        },
      ],
    })

    createApp(agentModule.default).use(pinia).mount('#visual-root')
  })

  await page.locator('.secondary-button').click()
  await page.locator('.insight-card').waitFor()
  await mkdir('../output/playwright', { recursive: true })

  const result = await page.evaluate((overlapSource) => {
    const overlap = new Function('left', 'right', `return (${overlapSource})(left, right)`)
    const scroll = document.querySelector('.agent-scroll')
    const selectors = ['.agent-scroll', '.message-timeline', '.plan-card', '.execution-sheet', '.insight-card', '.prompt-box']
    const samples = []
    for (const scrollTop of [0, 240, 480, 720, 960]) {
      if (scroll) scroll.scrollTop = scrollTop
      const rects = Object.fromEntries(selectors.map((selector) => {
        const element = document.querySelector(selector)
        if (!element) return [selector, null]
        const rect = element.getBoundingClientRect()
        const style = getComputedStyle(element)
        return [selector, {
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          left: rect.left,
          width: rect.width,
          height: rect.height,
          flex: style.flex,
        }]
      }))
      const pairs = [
        ['.execution-sheet', '.insight-card'],
        ['.agent-scroll', '.prompt-box'],
      ]
      const collisions = pairs.filter(([left, right]) => rects[left] && rects[right] && overlap(rects[left], rects[right]))
      samples.push({ scrollTop: scroll?.scrollTop ?? 0, rects, collisions })
    }
    return {
      samples,
      nextActionCount: document.querySelectorAll('.next-actions p').length,
      nextActionText: document.querySelector('.next-actions p')?.textContent ?? '',
    }
  }, overlaps.toString())
  await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false })

  await browser.close()
  if (result.nextActionCount !== 1) {
    throw new Error(`nextActions 渲染数量异常: ${result.nextActionCount}`)
  }
  const compressed = result.samples.filter((sample) => (sample.rects['.plan-card']?.height ?? 0) < 320)
  if (compressed.length) {
    throw new Error(`Agent 方案卡被 flex 压缩: ${JSON.stringify(compressed)}`)
  }
  const collided = result.samples.filter((sample) => sample.collisions.length)
  if (collided.length) {
    throw new Error(`Agent 布局发生重叠: ${JSON.stringify(collided)}`)
  }
  console.log(JSON.stringify({ ok: true, screenshot: SCREENSHOT_PATH, samples: result.samples }, null, 2))
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
