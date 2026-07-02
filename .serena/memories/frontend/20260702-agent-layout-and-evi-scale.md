# Agent布局与EVI尺度修复

## 一句话结论

- Agent 对话历史、方案卡、执行单和判读意见必须有独立流式布局约束；EVI 等带常数项指数必须使用 0-1 反射率语义，且明显越界值不得进入统计。

## 适用场景

- 用户反馈 Agent 面板中文本、按钮、执行单或判读意见重叠、历史对话不可见。
- 用户反馈 EVI/SAVI/OSAVI/EVI2/MSAVI 等结果均值或标准差出现数量级异常。

## 首选入口

- 路径：`frontend/src/components/AgentDrawer.vue`
- 关键文件：`backend/app/services/raster_pipeline.py`、`backend/app/engines/base.py`、`backend/app/core/indices.py`
- 推荐起点：先看 `AgentDrawer.vue` 的 `.message-timeline`、`.plan-card`、`.execution-sheet`、`.insight-card` 样式，再看 `raster_pipeline.py` 的 `_to_reflectance` 和 `base.py` 的 `sanitize_result`。

## 稳定约束 / 正确做法

- Agent 历史对话区域使用独立 max-height + overflow，不要让长历史直接挤压方案卡和输入框。
- 方案卡、判读卡、执行单和提交按钮都要设置 `min-width: 0`、合理 `line-height` 与 `overflow-wrap: anywhere`。
- `.agent-scroll` 是固定高滚动区内的纵向 flex 容器时，主要内容块必须设置 `flex: 0 0 auto`；否则 `.plan-card` 等 flex item 会被压缩到几十像素，内部执行单继续 `overflow: visible` 外溢，后续判读卡会按错误盒高排版并叠到执行单上。
- 不要在方案卡上使用会裁切内容的 `overflow: hidden`，否则窄屏下长文本和执行单容易被截断。
- Agent 判读结果属于 LLM / 兼容接口输出，前端不得信任 TypeScript 静态类型；`nextActions`、`insights`、`trace` 这类列表字段必须在 `usePlatformApi.ts` API 边界通过 `normalizeAgentInterpretation` 做运行期规整。
- Vue 的 `v-for` 会把字符串按字符迭代；若 `nextActions` 被模型返回为字符串，必须转成单条数组，否则会把“下一步”区域撑成大量段落并触发窄侧栏布局失控。
- RasterPipeline 读取整数型遥感波段后，先按 GeoTIFF scale/offset 转换；缺少元数据时再对常见 0-255、0-10000 反射率尺度做启发式归一化。
- 引擎输出清洗应结合 `IndexDefinition.expected_range`，把明显不可解释的病态分母结果写成 nodata，避免污染均值、标准差和判读意见。

## 常见误区

- 只修 CSS 字号不能解决重叠；必须给长文本容器和网格列加 `min-width: 0` 与换行规则。
- 看到判读卡压到执行单上时，不要只查 z-index；优先检查父级 flex 容器是否把前一个卡片压缩，以及实际 `getBoundingClientRect().height` 是否远小于内容高度。
- 只在后端规整 LLM 返回值不够；历史数据、测试 mock、兼容接口或后续调用方仍可能绕过后端防线，前端 API 解码层也必须兜底。
- 不能把 EVI 异常简单归因于公式写错；标准 EVI 公式正确，但它依赖 0-1 反射率尺度。
- 不能让 `safe_divide` 的 epsilon 独自处理病态分母；它只能防止 Inf/NaN，不能阻止巨大的有限异常值进入统计。

## 相关路由 / 文档

- `frontend/src/components/AgentDrawer.vue`
- `frontend/src/utils/agentInterpretation.ts`
- `frontend/src/components/AgentDrawer.spec.ts`
- `frontend/src/utils/agentInterpretation.spec.ts`
- `frontend/scripts/check-agent-layout.mjs`
- `backend/app/services/raster_pipeline.py`
- `backend/app/engines/base.py`
- `backend/tests/test_indices.py`
- `backend/tests/test_raster_pipeline.py`

## 验证基线

- 后端：`D:\miniconda\envs\giskeshe\python.exe -m ruff check .`
- 后端：`D:\miniconda\envs\giskeshe\python.exe -m pytest -q`
- 前端单测：`npm run test:unit`
- Agent 真实浏览器布局：先保证 `npm run dev` 在 5174 可访问，再运行 `npm run test:layout:agent`；该脚本必须覆盖 303×943 固定 Agent 面板，并检查 `.plan-card` 未被 flex 压缩、`.execution-sheet` 与 `.insight-card` 多滚动位置无相交。
- 前端：`npm run build`
- 窄屏视觉：Playwright 复现 `.agent-scroll`、`.plan-card`、`.insight-card` 子块无重叠，并保存到 `output/playwright/`。

## 关联 evidence

- `.evidence/active/20260702-2101-Agent布局与EVI尺度修复.md`
- `.evidence/active/20260703-0009-Agent判读卡布局复现与回归测试.md`

## 最后验证

- 时间：2026-07-02 21:01
- 验证人 / 来源：Codex，本地执行 Ruff、pytest、Vite build 与 Playwright MCP 视觉验证。
- 追加：2026-07-03 00:09，补充前端 API 边界运行期规整、Vitest 组件 / 纯函数测试和 `npm run test:layout:agent` 浏览器几何重叠检查。
- 修正：2026-07-03 00:23，用户二次截图确认仍重叠后，实际复现到核心根因是 `.agent-scroll` 内 flex item shrink；已通过 `flex: 0 0 auto` 和 303px 固定面板回归脚本覆盖。
