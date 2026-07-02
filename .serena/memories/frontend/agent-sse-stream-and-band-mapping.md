# 智能体 SSE 流式与波段映射修复

## 一句话结论

- 智能体前端已改用 `fetch` + `ReadableStream` 解析后端 `text/event-stream`，任务提交失败的关键根因是未用逻辑波段映射值为 `0` 也被后端全量校验。

## 适用场景

- 维护智能体对话流、方案生成、确认提交、任务状态展示或 GeoTIFF 波段映射时应读取。
- 用户反馈“方案生成后提交失败”“没有实时状态”“消息流不自动追加”时应读取。

## 首选入口

- 路径：`frontend/src/components/AgentDrawer.vue`
- 关键文件：`frontend/src/composables/usePlatformApi.ts`、`frontend/src/stores/workspace.ts`、`backend/app/api/routes.py`、`backend/app/services/raster_pipeline.py`
- 推荐起点：先看 `usePlatformApi.ts` 的 `requestStream`，再看 `AgentDrawer.vue` 的 `handlePlanStreamEvent` / `handleConfirmStreamEvent`，最后看后端 `/api/agent/*/stream` 路由。

## 稳定约束 / 正确做法

- 需要 POST JSON 请求体的流式接口不要用原生 `EventSource`，本项目采用 `fetch` 读取 `ReadableStream` 并解析 SSE 帧。
- 后端流式接口使用 `StreamingResponse(media_type="text/event-stream")`，事件类型包括 `status`、`plan`、`job`、`result`、`done`、`error`。
- 前端上传或选中影像后必须按 `metadata.count` 推断 `availableBands` 和 `bandMapping`；默认只暴露 4 波段 `blue/green/red/nir`，`red_edge/swir1/swir2` 默认为 `0`。
- 后端 RasterPipeline 只能校验本次指数实际需要的逻辑波段，不能校验 `task.bands` 里的所有值，否则未用波段 `0` 会导致 NDVI 等任务失败。
- 没有导入影像时，智能体确认按钮应禁用并显示“请先导入影像”。

## 常见误区

- 把 `red_edge/swir1/swir2` 默认加入 `availableBands` 会让智能体误判指数可执行。
- 异步任务失败不能只显示最终 `failed`，要把 job `error/message/status/progress` 写回智能体时间线。
- 后端测试里的 RAG 数据会影响意图分类，推荐结果异常不一定是 SSE 或任务执行失败。

## 关联 evidence

- `.evidence/active/20260702-1015-智能体SSE流式与任务失败修复.md`
- `output/playwright/agent-stream-layout.png`
- `output/playwright/agent-stream-after-plan.png`

## 相关路由 / 文档

- `backend/tests/test_api.py`
- `D:\.codex\docs\templates\memory-entry-template.md`

## 最后验证

- 时间：2026-07-02 10:15
- 验证人 / 来源：Codex，本地执行 Ruff、pytest、Vite build 与 Playwright 浏览器验证。