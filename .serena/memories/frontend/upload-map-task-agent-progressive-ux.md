# 上传、地图、任务与 Agent 渐进式体验优化

## 一句话结论

- 上传体验采用分阶段状态，但上传栏必须保持单行高信号状态，不显示会被裁切的底部详情；地图只允许导入完成首次定位和用户点击定位改变视角，定位 zoom 上限为 16；计算必须使用原始 GeoTIFF window 读取原图波段；地图显示有 TIF 时优先用原图/结果 TIF 动态瓦片，PNG 缩略图只作为无 TIF 时兜底；TIF 瓦片使用影像级统一拉伸统计，避免每块瓦片单独拉伸造成边缘色差；Agent 输入区固定贴底，状态信息收进标题细栏，内容中段只保留一个外层滚动，思考过程只展示高层 `thought/status` SSE，完整 trace 折叠在方案详情里。

## 适用场景

- 维护上传进度、GeoTIFF/COG 动态瓦片、MapLibre 自动定位、多指数结果切换、任务管理器字段或 Agent 对话布局时应读取。
- 用户反馈“上传 100% 像卡住”“上传栏遮住工作区”“地图一直抢视角”“默认缩放等级不要 14”“导入影像缩略图边缘色差大”“结果边界不准”“切指数地图不跟着变”“任务状态不够清楚”“Agent 输入框被方案挤走”“Agent 空态很怪”“检索来源重复太长”“思考过程重叠或不具体”“右侧栏多层滚动难读”时应读取。

## 首选入口

- 路径：`frontend/src/components/MapWorkspace.vue`
- 关键文件：`frontend/src/components/AssetToolbar.vue`、`frontend/src/components/JobProgressPanel.vue`、`frontend/src/components/AgentDrawer.vue`、`frontend/src/stores/workspace.ts`、`backend/app/services/raster_pipeline.py`、`backend/app/services/jobs.py`、`backend/app/services/tiles.py`、`backend/app/api/routes.py`
- 推荐起点：先看 `workspace.ts` 的 `activeResult / activeProductIndex`，再看 `MapWorkspace.vue` 的 `DEFAULT_LOCATE_MAX_ZOOM / adaptiveMaxZoom()`、`syncMapLayers()`、导入 asset watcher 和 tile source `bounds`，然后看 `tiles.py` 的 `_tile_stretches_cached()` 与 `render_geotiff_tile()`，最后看 `AgentDrawer.vue` 的 `agent-header-status / agent-scroll / thinkingSteps / visibleTraceSteps / visibleSources` 与 `routes.py` 的 `/api/agent/plan/stream`。

## 稳定约束 / 正确做法

- 上传 100% 后不要直接显示“完成”；如果 XHR 已到 100 但后端响应未返回，应显示“正在解析影像元数据”。
- 上传栏高度有限，不能再显示“已按影像范围定位，TIF瓦片将按视野渐进加载”这类低价值长提示；完成后只显示“已导入…”；上传中把阶段、百分比、文件名合并到一行，避免底部 `small` 被裁切。
- 地图同步图层和移动视角必须分离；`syncMapLayers()` 只做图层同步，不允许调用 `fitBounds()`。
- 只有两类动作可以改变地图 zoom/center：导入完成后的首次 source bounds 定位，以及用户点击图层面板里的“定位”按钮。
- 定位 zoom 上限固定从 `DEFAULT_LOCATE_MAX_ZOOM = 16` 起步，小 footprint 应定位到 16；较大 footprint 再由 `adaptiveMaxZoom()` 递减，避免大范围影像过度放大。
- 结果切换、图层开关、透明度变化、显示模式变化和 tile demand 更新都必须保持当前缩放等级和中心点。
- 计算链路必须使用原始 GeoTIFF：`raster_pipeline.py` 通过 Rasterio window 读取原图波段并输出 GeoTIFF/COG；PNG/缩略图不得参与植被指数计算。
- 地图展示有 `objectKey`/TIF 瓦片时必须优先使用 TIF raster source，不要同时叠加 PNG 缩略图；PNG 预览只在没有 TIF 瓦片源时兜底。
- 输入影像和结果都可以保留 PNG 预览文件用于兜底或列表缩略图，但地图主视图优先 TIF 动态瓦片；TIF raster source 必须设置 `bounds`，让 MapLibre 只请求当前视野内且落在影像范围内的瓦片。
- 后端瓦片缓存缓存 PNG bytes，不缓存 Rasterio dataset 句柄；缓存键应包含 objectKey、z/x/y、mtime 和 size。
- TIF 瓦片颜色拉伸应按影像级缓存统一 2/98 百分位范围，不要每个瓦片单独计算百分位；有效像元 alpha 应保持不透明，避免底图透出造成边缘色差。
- 任务管理器展示新字段：`started_at / finished_at / eta_seconds / throughput / current / total / engine / index_count`；前端对缺失字段保留估算兜底。
- Agent 的“待命 / 规则引擎兜底 / 网络检索开启 / NEW SESSION”属于标题状态栏，不应放在对话中部做大卡片或方块 chip。
- Agent 的中段布局应按块顺序滚动：对话区、思考过程区、方案详情区；只保留 `.agent-scroll` 一个外层滚动，消息列表和思考区不要再各自设置 `overflow: auto` 或最大高度滚动。
- Agent 思考过程只展示高层流式步骤，不要合并完整 `activePlan.trace`；后端 SSE 也不要把完整 trace 逐条推送到思考区。完整 trace 保留在方案详情里的折叠“运行过程”。
- “收起/展开详情”属于方案卡片动作，必须放在方案标题栏右侧，不要放回对话区或思考区附近；方案详情默认收起，避免生成后直接铺满右侧栏。
- Agent 头部的“知识库/配置”按钮必须保持不逐字换行，窄栏下用最小宽度和 `white-space: nowrap`。
- Agent 的 job 轮询和确认任务 `status/done` 事件只更新 `store.jobs` 或轻量执行摘要，不要每次追加聊天消息；任务状态主入口是任务管理器。
- `/api/agent/plan/stream` 的 `thought` 事件应输出具体上下文：影像尺寸、可用波段、外部资料数量、推荐指数、可执行数量、推荐引擎、估算内存和人工确认边界；避免只输出重复的“理解问题”。
- Agent 检索来源必须按 `title/source/content` 去重，默认折叠，避免重复知识卡片挤占输入和对话空间。

## 常见误区

- 把 `fitBounds()` 放回 asset/product watcher 或 `syncMapLayers()` 会重新引入抢视角问题。
- 将定位上限改回 14/13 会违背当前 UX 约束；小范围影像默认定位目标应是 16。
- 通过 `moveend` 反复 add/remove TIF source 会让渐进加载本身变慢；优先用 raster source `bounds` 约束请求范围。
- 上传完成后展示长句解释会重新造成工具栏裁切；需要解释时放到任务管理器或 Agent 消息，不放在上传栏。
- 不要让 PNG 缩略图和 TIF 瓦片同时叠在地图主视图上，否则边缘配准和透明度会造成明显色差。
- 不要用每块瓦片自己的 percentile 拉伸显示 TIF，否则边界、瓦片缝和结果边缘会出现亮度/颜色跳变。
- Agent 侧栏里不要同时让 `.agent-scroll`、`.message-timeline`、`.thinking-panel` 三层滚动；多层滚动会再次造成遮蔽和阅读错位。
- 不要把完整 `plan.trace` 同时显示在思考过程和运行过程里；高层思考和完整运行细节必须分层。
- 多指数切换不要在地图、统计、任务面板各自维护一份当前指数；统一走 `store.selectActiveProduct()`。
- 任务状态主视图是任务管理器，Agent 对话只保留解释、建议、完成和错误等低频事件。

## 关联 evidence

- `.evidence/active/20260702-1216-上传地图任务Agent体验优化.md`

## 相关路由 / 文档

- `frontend/src/components/MapWorkspace.vue`
- `frontend/src/components/AssetToolbar.vue`
- `frontend/src/components/JobProgressPanel.vue`
- `frontend/src/components/AgentDrawer.vue`
- `backend/app/api/routes.py`
- `backend/app/services/raster_pipeline.py`
- `backend/app/services/jobs.py`
- `backend/app/services/tiles.py`
- `D:\.codex\docs\templates\memory-entry-template.md`

## 最后验证

- 时间：2026-07-02 13:19 +08:00
- 验证人 / 来源：Codex，本地执行 Ruff、pytest API、完整 pytest、Vite build、diff 空白检查；本轮主要为 Agent 去重折叠、地图 TIF 优先和瓦片统一拉伸。