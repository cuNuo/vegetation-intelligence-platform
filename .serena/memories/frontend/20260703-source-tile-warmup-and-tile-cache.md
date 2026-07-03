# 原图 TIF 瓦片预热与后端瓦片缓存

## 背景

2026-07-03 用户反馈原图瓦片加载不出来且很慢。定位到 `frontend/src/components/MapWorkspace.vue` 的 `source-tiles` 与 `backend/app/services/tiles.py` 动态瓦片渲染链路。

## 结论

- 当上传原图存在 PNG preview 时，不能把 `source-tiles` 长时间保持 `raster-opacity = 0` 再依赖 `isSourceLoaded('source-tiles')` 切换；MapLibre 可能不积极请求全透明 raster layer，导致“预览就绪，原图瓦片加载中”卡住。
- 当前做法：在原图范围进入视野且源图层开启时，用 `SOURCE_TILE_WARMUP_OPACITY = 0.01` 预热 TIF 瓦片；`isSourceLoaded('source-tiles')` 后再切到 0.92。
- 后端 `tiles.py` 已增加 `TileDatasetInfo` / `_tile_dataset_info_cached()`，缓存 WebMercator 范围和显示波段；范围外瓦片在打开数据集重投影前返回空瓦片；`_empty_tile()` 缓存单例 PNG bytes。

## 验证

- Ruff：`python -m ruff check backend/app/services/tiles.py` 通过。
- Pytest：`backend/tests/test_api.py::test_geotiff_tile_endpoint_renders_uploaded_tif` 通过。
- 前端：`npm run build` 通过，保留既有 chunk size warning。
- Playwright：上传 `data/test/bajiepart1.tif` 后捕获 4 个原图瓦片请求，全部 200；MapLibre `source-tiles` 存在，`isSourceLoaded=true`，`raster-opacity=0.92`。
- 证据：`.evidence/active/20260703-1219-原图瓦片加载性能优化.md`，截图 `output/playwright/source-tile-warmup-20260703.png`。

## 后续注意

- 1% 透明度预热是最小前端修复，视觉影响低；如用户继续反馈超大图加载慢，应评估 COG/静态瓦片/TileJSON 或服务端瓦片队列，而不是继续叠加前端状态判断。
- 全局 Hook `audit-directory-antipatterns` 仍会因既有单文件目录失败，非本轮新增。