# 2026-07-02 Vite 单配置与天地图空状态

- 用户报告 `npm run dev -- --host 127.0.0.1 --port 5174` 在当前 shell/npm 链路中被转成 `vite 127.0.0.1 5174`，导致 Vite 按默认 `localhost:5173` 启动。
- 修复：`frontend/package.json` 的 `dev` 脚本改为 `vite --host 127.0.0.1 --port 5174`；`frontend/vite.config.js` 增加 `server.host = '127.0.0.1'` 与 `strictPort = true`。后续启动前端直接运行 `npm run dev`，不要追加 `-- --host ... --port ...`。
- 配置收敛：删除 `frontend/vite.config.ts` 与 `frontend/vite.config.d.ts`，只保留 `frontend/vite.config.js`；`frontend/tsconfig.node.json` 改为检查 `vite.config.js`。
- 地图空状态：`MapWorkspace.vue` 中底图图层始终显示，导入影像/计算结果只作为叠加层；未导入栅格时仍保持左侧地图工作区、右侧智能体布局。
- 安全边界：天地图 Token 不写入源码；使用 `VITE_TIANDITU_TOKEN` 从本地 `.env` 或部署环境注入。若未配置，地图左下角提示“天地图 Token 未配置”。
- 验证：`npm run build` 通过，仅 Vite 大 chunk 警告；前端重启日志显示 `Local: http://127.0.0.1:5174/`；Playwright 截图 `output/playwright/tianditu-agent-layout-20260702.png` 验证左图右智能体布局。提交标题：`fix: stabilize vite dev server and map empty state`。