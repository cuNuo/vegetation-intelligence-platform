# 上传、地图、任务与 Agent 渐进式体验优化

## 一句话结论

- 上传体验采用分阶段状态，但上传栏必须保持单行高信号状态，不显示会被裁切的底部详情；地图只允许导入完成首次定位和用户点击定位改变视角，定位 zoom 上限为 16；计算必须使用原始 GeoTIFF window 读取原图波段；地图显示有 TIF 时优先用原图/结果 TIF 动态瓦片，PNG 缩略图只作为无 TIF 时兜底；TIF 瓦片使用影像级统一拉伸统计，避免每块瓦片单独拉伸造成边缘色差；Agent 输入区固定贴底，状态信息收进标题细栏，思考过程用前端队列逐条展示高层 `thought/status` SSE，完整 trace 折叠在方案详情里；执行单和确认提交入口必须始终可见，不依赖详情展开；任务管理器完成结果必须支持导出 TIF。

## 稳定约束 / 正确做法

- 上传 100% 后不要直接显示“完成”；如果 XHR 已到 100 但后端响应未返回，应显示“正在解析影像元数据”。
- 地图同步图层和移动视角必须分离；`syncMapLayers()` 只做图层同步，不允许调用 `fitBounds()`。
- 只有两类动作可以改变地图 zoom/center：导入完成后的首次 source bounds 定位，以及用户点击图层面板里的“定位”按钮。
- 定位 zoom 上限固定从 `DEFAULT_LOCATE_MAX_ZOOM = 16` 起步，小 footprint 应定位到 16；较大 footprint 再由 `adaptiveMaxZoom()` 递减。
- 计算链路必须使用原始 GeoTIFF：`raster_pipeline.py` 通过 Rasterio window 读取原图波段并输出 GeoTIFF/COG；PNG/缩略图不得参与植被指数计算。
- 地图展示有 `objectKey`/TIF 瓦片时必须优先使用 TIF raster source，不要同时叠加 PNG 缩略图；PNG 预览只在没有 TIF 瓦片源时兜底。
- 后端瓦片缓存缓存 PNG bytes，不缓存 Rasterio dataset 句柄；TIF 瓦片颜色拉伸应按影像级缓存统一 2/98 百分位范围，不要每个瓦片单独计算百分位；有效像元 alpha 应保持不透明。
- Agent 的中段布局应按块顺序滚动：对话区、思考过程区、方案卡片；思考区可有自己的高度边界来防重叠，但执行单和提交按钮不能被详情折叠隐藏。
- Agent 思考过程只展示高层流式步骤，不要合并完整 `activePlan.trace`；后端 SSE 也不要把完整 trace 逐条推送到思考区。完整 trace 保留在方案详情里的折叠“运行过程”。
- 前端应对 thought/status 做节流队列展示，避免后端快速返回时所有步骤瞬间蹦出；当前节奏约 360ms 一条。
- “收起/展开详情”属于方案卡片动作，详情只放解释、运行 trace、来源和质量提示；方案摘要、可执行指数、指数勾选、引擎、block size、优先级、确认提交按钮必须始终可见。
- Agent 的 job 轮询和确认任务 `status/done` 事件只更新 `store.jobs` 或轻量执行摘要，不要每次追加聊天消息；任务状态主入口是任务管理器。
- 任务管理器完成任务后应在每个产品旁提供“导出TIF”，链接到对应产品的 GeoTIFF artifact；不要只提供“打开结果”。

## 常见误区

- 把 `fitBounds()` 放回 asset/product watcher 或 `syncMapLayers()` 会重新引入抢视角问题。
- 将定位上限改回 14/13 会违背当前 UX 约束；小范围影像默认定位目标应是 16。
- 不要让 PNG 缩略图和 TIF 瓦片同时叠在地图主视图上，否则边缘配准和透明度会造成明显色差。
- 不要用每块瓦片自己的 percentile 拉伸显示 TIF，否则边界、瓦片缝和结果边缘会出现亮度/颜色跳变。
- 不要把完整 `plan.trace` 同时显示在思考过程和运行过程里；高层思考和完整运行细节必须分层。
- 不要把执行指数和提交按钮放进 `isDetailsOpen` 分支；用户收起详情后仍要能确认任务。

## 关联 evidence

- `.evidence/active/20260702-1216-上传地图任务Agent体验优化.md`

## 最后验证

- 时间：2026-07-02 13:40 +08:00
- 验证人 / 来源：Codex，本地执行 Ruff、pytest API、完整 pytest、Vite build、diff 空白检查；本轮主要为执行单外置、思考节流和任务管理器 TIF 导出。