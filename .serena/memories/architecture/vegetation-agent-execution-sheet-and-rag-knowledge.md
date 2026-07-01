# Agent 可编辑执行单与外部知识库

- 2026-06-23 新增 `backend/app/services/agent_knowledge_store.py`，用于 Agent 外部知识库存储和召回。配置 `VIP_DATABASE_URL` 时写 PostgreSQL 表 `vegetation_agent_knowledge_documents`，否则内存降级。
- 新增 API：`POST /api/agent/knowledge`，请求字段 `title/content/source/sessionId`，用于导入指数说明、适用场景、限制和判读经验。导入内容只参与 RAG，不触发命令或任务提交。
- `search_index_knowledge` 召回顺序包括：内置指数库、请求级外部文档、持久知识库。中文词项已覆盖黄化、氮素、设施农业、病虫害、灌溉等常见场景。
- Agent 确认执行改为可编辑执行单：`ConfirmPlanRequest` 支持 `indices/engine/blockSize/priority`。后端会重新校验 `indices` 必须来自当前 plan 的 executable recommendations，禁止绕过缺波段或未推荐指数检查。
- `VegetationAgent.mark_confirmed` 会把最终执行单写回 plan 和会话事件 payload。前端 `AgentDrawer.vue` 已有执行单 UI：指数复选框、引擎选择、block size、优先级；另有知识导入区，支持粘贴文本或读取 `.txt/.md/.csv` 文件内容。
- `/api/system/capabilities` 返回 `agentKnowledgeStorage`，取值 `postgresql` 或 `memory`。
- 验证：Ruff 通过；pytest 29 passed；frontend `npm run build` 通过但保留 MapLibre/ECharts 大 chunk warning。