# 2026-07-02 地图图层、智能体对话与公式 UX

- 地图工作区已改成左侧 ArcGIS 风格图层面板：底图、导入影像、计算结果、范围框各自有显隐开关；支持“只看底图”和“恢复分析图层”。
- 上传 `bajiepart1.tif` 后需要自动定位到影像范围；小范围影像使用 `easeTo(center, zoom=14)`，普通范围继续使用 `fitBounds`。这是为了避免 MapLibre 对超小 bounds 或图像源刚添加时定位不稳定。
- 计算前、计算后、对比按钮不只是改透明度，还要调用定位逻辑追踪到对应图层范围。
- 智能体主面板改为对话优先：用户输入先写入本地对话流，再等待后端方案；知识库导入移动到弹窗；方案详情、来源和执行单收敛到可展开区域。
- 公式展示改为轻量类 LaTeX 分式渲染，不使用 `v-html`。`IndexCatalog.vue` 只拆最外层除号，避免括号内部表达式被误拆。
- 已删除首屏说明、页脚说明、上传预览解释、每张指数卡重复限制句等冗余文案。
- 验证：`npm run build` 通过，仅 Vite chunk size 警告。Playwright 截图包括 `output/playwright/ux-map-upload-fit-easeto-20260702.png`、`output/playwright/ux-map-basemap-only-mcp-20260702.png`、`output/playwright/ux-agent-knowledge-modal-20260702.png`。
- 证据日志：`.evidence/active/20260702-0200-地图图层智能体公式UX优化.md`。
