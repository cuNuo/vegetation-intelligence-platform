# 前端响应式主题与应用壳

- 2026-06-22继续完善前端，新增 `useTheme.ts`，支持light/dark主题、localStorage持久化和`data-theme` CSS变量切换。
- 新增 `AppToolbar.vue`、`AppStatusBar.vue`、`AssetToolbar.vue`；顶部工具栏支持工作区导航、服务刷新、主题切换、AI/任务/指数面板显隐；底部状态栏展示API、引擎、CUDA、队列、结果和时间。
- `App.vue`改为最高2200px的全宽流式工作台，1100px以下主区上下排列，760px以下遥测面板单列。
- `MapWorkspace.vue`和`StatisticsDashboard.vue`使用ResizeObserver，窗口和面板宽度变化后自动调用map/chart resize。
- Playwright验证：900/1440/1920宽度无横向溢出，地图宽度856/980/1399；隐藏AI后地图从980扩到1374；light主题背景#f6f7f2且刷新后保持。
- 后端测试扩展到20项，覆盖真实GeoTIFF同步、异步、批量、错误路径、变化检测、地块统计等任务书主链。