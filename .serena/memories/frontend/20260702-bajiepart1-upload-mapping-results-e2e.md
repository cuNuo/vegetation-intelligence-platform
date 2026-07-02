# 2026-07-02 bajiepart1 真实数据上传、映射、Agent 计算和多指数切换验证

## 核心结论

- 测试数据：`data/test/bajiepart1.tif`，约 510MB，6376 x 3194，6 波段，CRS 为 EPSG:32650。
- 该影像 `descriptions` 全为空，`bandMetadata[*].wavelengthNm` 全为空，标签只有统计信息，因此无法真正按波长自动映射。
- 当前前端正确降级为常见顺序兜底，并在“逻辑波段”弹窗提示“6 个源波段，无波长元数据，按常见顺序兜底”。
- 实际映射：Blue=1、Green=2、Red=3、Red Edge=5、NIR=4、SWIR1=6、SWIR2=0。
- 浏览器端到端验证通过：上传进度有百分比采样，映射弹窗可点击，Agent 计划包含 NDVI/EVI/GNDVI，确认提交后任务 successful，统计面板可切换多个指数。

## 相关改动

- `backend/app/services/assets.py` 的 `inspect_raster()` 返回 `bandMetadata`，包含 `band / description / tags / wavelengthNm`。
- `frontend/src/stores/workspace.ts` 自动映射优先级：波长元数据 -> 描述关键词 -> 常见顺序兜底 -> 手动修正。
- `frontend/src/components/AssetToolbar.vue` 将映射编辑放入点击“逻辑波段”后的弹窗，显示源波段证据，并修复工具栏被地图浮层截获点击的问题。
- `frontend/src/composables/usePlatformApi.ts` 上传使用 XHR 进度回调，并增强上传错误解析。
- `frontend/src/components/JobProgressPanel.vue`、`StatisticsDashboard.vue`、`App.vue` 和 `workspace.ts` 支持同一结果组内多指数切换。

## 验证证据

- 真实后端批处理：`/processes/batch/execution` 输入 NDVI/EVI/GNDVI，numpy 引擎约 25.9 秒完成，三个输出 COG 和预览均存在。
- Playwright 证据脚本：`output/playwright/validate-ui.cjs`。
- 截图：`output/playwright/band-mapping-modal.png`、`output/playwright/multi-index-results.png`。
- Evidence：`.evidence/active/20260702-1055-bajiepart1真实数据端到端验证.md`。

## 后续注意

- 若要验证“按波长自动映射”命中路径，需要补一份带中心波长标签的 GeoTIFF，例如包含 `wavelength`、`central_wavelength`、`BandName` 或描述中带 `665 nm` / `0.842 um` 的测试影像。
- `bajiepart1.tif` 只能验证无波长元数据时的可解释降级和手动修正入口。