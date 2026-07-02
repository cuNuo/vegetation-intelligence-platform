# 2026-07-02 结果图层缩放体验优化与用户手册

## 稳定结论

- `MapWorkspace.vue` 的源影像与结果 TIF raster source 使用 `maxzoom=16`，地图交互 `maxZoom=19`。
- 16 级以上不再继续请求后端更高 zoom 动态瓦片，而是由 MapLibre 复用 16 级瓦片平滑放大，避免高缩放级别反复触发 Rasterio 重投影导致卡顿。
- 图层面板新增“缩放策略”，显示 `缩放 X，动态瓦片` 或 `缩放 X，复用 16 级瓦片`；源图层/结果图层状态在高倍时显示“16级后平滑放大”。
- 后端 `/api/tiles/{z}/{x}/{y}.png` 返回 `Cache-Control: public, max-age=86400, immutable`；`tiles.py` 对非法 XYZ 编号和影像范围外瓦片直接返回透明 PNG。

## 验证与产物

- Playwright 脚本：`output/playwright/validate-result-layer-zoom-ux.cjs`。
- 关键验证结果：18 级缩放时 `highZoomTileCount=0`、`failedTiles=[]`、`highZoomOverLimitTiles=[]`、`sourceMaxzoom=16`。
- 截图：`output/playwright/result-layer-manual-03-result-map.png`、`output/playwright/result-layer-manual-04-high-zoom.png`。
- 用户手册：`docx/结果图层缩放与浏览用户手册.docx`，由 `docx/build_result_layer_manual.py` 生成。
- evidence：`.evidence/active/20260702-2206-结果图层缩放性能与用户手册.md`。

## 后续注意

- 不要把结果图层 `maxzoom` 改回默认 22，否则高倍缩放会恢复大量后端瓦片请求。
- 如果未来需要 16 级以上真实细节，应优先实现离线瓦片金字塔/COG overview 服务，而不是让浏览器直接请求更高 z 的动态重投影。
- 全局 `run_relevant_hooks.py --changed-only` 仍会因仓库既有单文件目录反模式失败；本轮不是新增问题。