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
- 不要在方案卡上使用会裁切内容的 `overflow: hidden`，否则窄屏下长文本和执行单容易被截断。
- RasterPipeline 读取整数型遥感波段后，先按 GeoTIFF scale/offset 转换；缺少元数据时再对常见 0-255、0-10000 反射率尺度做启发式归一化。
- 引擎输出清洗应结合 `IndexDefinition.expected_range`，把明显不可解释的病态分母结果写成 nodata，避免污染均值、标准差和判读意见。

## 常见误区

- 只修 CSS 字号不能解决重叠；必须给长文本容器和网格列加 `min-width: 0` 与换行规则。
- 不能把 EVI 异常简单归因于公式写错；标准 EVI 公式正确，但它依赖 0-1 反射率尺度。
- 不能让 `safe_divide` 的 epsilon 独自处理病态分母；它只能防止 Inf/NaN，不能阻止巨大的有限异常值进入统计。

## 相关路由 / 文档

- `frontend/src/components/AgentDrawer.vue`
- `backend/app/services/raster_pipeline.py`
- `backend/app/engines/base.py`
- `backend/tests/test_indices.py`
- `backend/tests/test_raster_pipeline.py`

## 验证基线

- 后端：`D:\miniconda\envs\giskeshe\python.exe -m ruff check .`
- 后端：`D:\miniconda\envs\giskeshe\python.exe -m pytest -q`
- 前端：`npm run build`
- 窄屏视觉：Playwright 复现 `.agent-scroll`、`.plan-card`、`.insight-card` 子块无重叠，并保存到 `output/playwright/`。

## 关联 evidence

- `.evidence/active/20260702-2101-Agent布局与EVI尺度修复.md`

## 最后验证

- 时间：2026-07-02 21:01
- 验证人 / 来源：Codex，本地执行 Ruff、pytest、Vite build 与 Playwright MCP 视觉验证。
