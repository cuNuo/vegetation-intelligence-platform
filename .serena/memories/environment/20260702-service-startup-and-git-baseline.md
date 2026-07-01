# 2026-07-02 服务启动与 git 基线

- 用户反馈无法启动服务，复现后端启动时 FastAPI startup 成功，但 `127.0.0.1:8011` 绑定失败；根因是旧的 `uvicorn app.main:app --reload` 进程占用端口。
- 已重启后端与前端开发服务：后端 `http://127.0.0.1:8011`，前端 `http://127.0.0.1:5174`。
- 健康验证：`/api/system/capabilities` 返回 `cuda: true`、`indexCount: 30`、`asyncJobs: true`、PostgreSQL/MinIO/RAG 状态；前端首页返回 200。
- 验证命令：后端 `ruff check .` 通过；后端 `pytest -q` 为 29 passed，1 个 Starlette TestClient 上游弃用警告；前端 `npm run build` 通过，仅 Vite 大 chunk 警告。
- Git 维护：建立初始提交 `685c03b chore: establish project baseline`，提交后 `git status --short --branch` 为干净 `## main`。
- 忽略规则已覆盖本地生成物：`%SystemDrive%/`、`texput.log`、`data/`、`output/`、`.playwright-mcp/`、`backend/*.egg-info/`。
- 安全修正：移除 `frontend/src/components/MapWorkspace.vue` 中硬编码天地图 Token，改用 `import.meta.env.VITE_TIANDITU_TOKEN`；`.env.example` 只保留空占位；`frontend/tsconfig.app.json` 增加 `vite/client` 类型。
- 证据日志：`.evidence/active/20260702-0045-服务启动与git维护.md`。