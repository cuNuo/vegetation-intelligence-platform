# 前端地图图层控制与指数库修复

- 2026-06-25 修复前端遥感工作台可读性和地图交互。
- 实际生效的 Vite 配置文件是 `frontend/vite.config.js`；它曾指向旧端口 `localhost:8000`，会导致 `/api/indices`、`/jobs`、`/api/system/capabilities` 在前端端口返回 500。当前默认代理应为 `http://127.0.0.1:8011`，同时保留 `VITE_API_TARGET` 覆盖。
- `MapWorkspace.vue` 现在接收 `asset` 与 `product`：导入资产有 WGS84 合法 bounds 时显示“计算前”空间范围；计算结果有 `previewPath` 时显示“计算后”PNG 图层；右下角提供天地图矢量、影像、地形三类底图和计算前/计算后/对比模式。
- 上传 GeoTIFF 目前没有上传预览 PNG 或瓦片接口，浏览器不能直接把 GeoTIFF 本体作为 MapLibre image source 渲染。若后续要真正叠加计算前像素，需要后端在上传阶段生成 preview PNG 或提供瓦片服务。
- 指数库 `IndexCatalog.vue` 已改成可读卡片，展示公式、所需波段、期望范围和限制；状态栏会显示指数库数量，正常应为 30。
- 本次验证：`npm run build` 通过；前端端口 `/api/indices` 返回 200；Playwright 快照显示 `API 在线` 和 `指数库 30 个`。