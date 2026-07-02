# 手动植被指数提取弹窗

## 一句话结论

- 右上角原“批量处理”入口已改为“植被指数提取”，由 `AssetToolbar.vue` 打开手动多指数选择弹窗，并复用现有批量异步任务接口推送到任务管理器。

## 适用场景

- 维护影像导入后的手动指数计算入口。
- 用户反馈想手动选择多个植被指数，而不是依赖 Agent 推荐或默认 NDVI。
- 调整指数搜索、分类筛选、缺失波段禁用原因或任务提交提示。

## 首选入口

- 路径：`frontend/src/components/AssetToolbar.vue`
- 关键文件：`frontend/src/composables/usePlatformApi.ts`、`frontend/src/stores/workspace.ts`、`frontend/src/types/platform.ts`
- 推荐起点：先看 `openIndexExtraction`、`filteredIndexCards`、`toggleManualIndex` 和 `submitManualIndexExtraction`，再看 `usePlatformApi.executeAssetBatch`。

## 稳定约束 / 正确做法

- 指数可执行性由 `IndexMetadata.requiredBands` 与 `store.asset.availableBands` 派生，不要硬编码 NDVI/EVI 等特殊判断。
- 缺失波段的指数必须禁用，并显示 `缺少 Blue / Red Edge / SWIR` 等可读原因。
- 弹窗提交继续复用 `/processes/batch/execution`，任务管理器由 App 全局轮询刷新。
- 没有导入影像时入口按钮保持禁用；没有指数目录时提示用户刷新服务状态。

## 常见误区

- 不要把搜索和分类筛选写成静态列表；后端注册表可能新增自定义指数。
- 不要允许缺失波段的指数提交到后端再失败；前端应先阻断。
- 不要绕过 `usePlatformApi.ts` 重写 fetch 调用。

## 关联 evidence

- `.evidence/active/20260702-2153-手动植被指数提取弹窗.md`

## 相关路由 / 文档

- `frontend/src/components/AssetToolbar.vue`
- `frontend/src/composables/usePlatformApi.ts`
- `frontend/src/stores/workspace.ts`
- `frontend/src/types/platform.ts`

## 最后验证

- 时间：2026-07-02 21:53
- 验证人 / 来源：Codex，本地执行 Vite build、Playwright MCP 入口检查和文件头 Hook。
