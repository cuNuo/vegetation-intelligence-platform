# LAD08 上传波段与地图定位性能修复

## 一句话结论

- 上传 UUID 不再破坏 LAD08/LAD09 传感器识别；地图保持当前底图常驻，上传响应后约 117 ms 启动定位，preview 先显示、TIF 就绪后接管。

## 适用场景

- 用户反馈上传后的 Landsat 波段映射错误、Red Edge/NIR 重复、自动定位迟迟不动、地图导入后空白或底图请求过多时读取。
- 维护 `MapWorkspace.vue` 的底图、定位、栅格 source 或 `workspace.ts` 波段推断时读取。

## 首选入口

- 路径：`frontend/src/components/MapWorkspace.vue`
- 关键文件：`backend/app/services/assets.py`、`backend/tests/test_assets.py`、`frontend/src/stores/workspace.ts`、`frontend/src/components/AssetToolbar.vue`
- 推荐起点：先看 `inspect_raster(filename_hint)` 和 `inferBandMapping()`，再看 `mapReady`、`syncSourceLayer()`、`ensureBasemapLayers()`。

## 稳定约束 / 正确做法

- 上传文件可继续使用 UUID 存储，但检查传感器配置时必须传原始上传文件名。
- 存在可靠波长或描述时，从全部逻辑波段未映射开始推断，不得保留通用波段数兜底。
- Landsat 8/9 映射：Blue=2、Green=3、Red=4、NIR=5、SWIR1=6、SWIR2=7，Red Edge=0；B1 是 Coastal Aerosol。
- 当前选中的天地图底图必须始终显示；未选底图按需添加，不在初始化时同时请求三套底图。
- 自动定位只依赖地图初始 load，不依赖 `idle` 或新增 source 后的 `isStyleLoaded()`。
- 相同 URL/bounds 的 source 不得因透明度或图层开关变化而 remove/add。
- preview 位于底图上方，TIF 初始透明；`isSourceLoaded('source-tiles')` 后切换到 TIF。
- 响应式资产工具栏必须由实际网格行数决定高度，禁止第二行控件溢出到地图上。

## 常见误区

- `file.filename` 与 UUID 保存名不是同一个语义；传感器识别不能只看保存路径。
- 把 fallback 先填满再覆盖波长会残留不存在的 Red Edge。
- MapLibre `idle` 会等待可见瓦片和动画，不能作为定位前置条件。
- `addSource()` 后 `isStyleLoaded()` 可能短暂为 false，但不会再次触发初始 `style.load`，会造成自动定位丢失。
- 每次 `syncMapLayers()` 删除重建 raster source 会重复请求瓦片。

## 关联 evidence

- `.evidence/active/20260702-1932-LAD08波段与地图定位性能修复.md`

## 相关路由 / 文档

- `README.md`
- `docs/superpowers/specs/2026-07-02-upload-locate-performance-design.md`
- `output/playwright/lad08-mapping-locate-optimized.png`

## 最后验证

- 时间：2026-07-02 19:45
- 验证人 / 来源：Codex；真实浏览器 Playwright、Ruff、pytest、Vite build。
- 结果：定位启动延迟 117 ms；初始底图仅 img/cia；preview opacity=0、TIF opacity=0.92；后端 39 passed；前端构建通过。