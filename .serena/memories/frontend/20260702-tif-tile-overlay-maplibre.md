# 2026-07-02 MapLibre 使用 TIF/COG 动态瓦片叠加输入影像与计算结果

## 背景

用户指出：正式输出结果应该是 `.tif`，PNG 只能作为预览；天地图底图上也应该导入正常 TIF 来预览，否则无法放大查看细节。

## 结论

- 正式计算输出继续保持 GeoTIFF/COG：`Product.path` 指向 `.tif`。
- PNG 预览只作为兜底，不再作为主地图叠加路径。
- 地图主路径改为 TIF 动态 XYZ 瓦片：`/api/tiles/{z}/{x}/{y}.png?key=...`。
- 输入影像使用 `UploadedAsset.objectKey`，计算结果使用 `Product.objectKey`，前端 MapLibre 创建 `type: raster` 的 tile source。

## 关键实现

- `backend/app/services/tiles.py`
  - `resolve_tile_key(key)`：只允许读取 `settings.data_dir` 下的 objectKey，避免任意路径读取。
  - `render_geotiff_tile(key,z,x,y)`：使用 Rasterio `reproject()` 将 GeoTIFF/COG 重投影到 256x256 WebMercator tile，再用 PIL 输出 PNG tile。
  - 多波段输入按 3/2/1 RGB 渲染，单波段指数结果使用伪彩色渲染。
- `backend/app/api/routes.py`
  - 新增 `GET /api/tiles/{z}/{x}/{y}.png?key=...`。
- `backend/app/services/assets.py`
  - 开发模式下 `upload_artifact()` 也返回 objectKey，而不是 None。
  - 上传资产返回 `previewObjectKey`。
- `frontend/src/components/MapWorkspace.vue`
  - 优先用 `objectKey` 创建 `/api/tiles/{z}/{x}/{y}.png?key=...` 瓦片源。
  - 仅在没有 objectKey 时回退到 PNG `previewPath` image source。
  - 图层面板显示“源图层/结果图层：TIF 瓦片 / PNG 预览 / 未加载”。
  - 修复 MapLibre `isStyleLoaded()` 为 false 时结果图层同步被吞的问题：挂到 `idle` 后重试。
  - 固定图层顺序：`source-preview -> vegetation-result -> source-footprint-line`，确保结果层在源影像之上，范围线最上。

## 验证

- 后端测试：`pytest backend/tests/test_api.py backend/tests/test_agent.py -q`，24 passed。
- Ruff：通过。
- 前端 `npm run build`：通过，仅 Vite chunk size warning。
- Playwright：`output/playwright/validate-tif-tiles.cjs`。
  - 输入 TIF 瓦片请求 29 个，全部 200。
  - 输出 GNDVI TIF 瓦片请求 15 个，全部 200。
  - MapLibre style sources 同时存在 `source-preview` 和 `vegetation-result`，均为 `/api/tiles/...tif`。
  - 图层顺序为 `source-preview -> vegetation-result -> source-footprint-line`。
- 截图：`output/playwright/tif-tile-overlay-results.png`。

## 注意

- 8012/5175 是本轮验证临时服务；正式使用 8011/5174 时需重启后端加载新 `/api/tiles` 路由。
- 若从 `backend` 目录启动服务，建议显式配置 `VIP_DATA_DIR` 指向项目根 `data`，否则默认 `data` 会落到 `backend/data`。