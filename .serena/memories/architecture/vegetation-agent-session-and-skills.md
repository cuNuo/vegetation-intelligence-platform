# Agent 会话持久化与 skill 收拢

- 2026-06-23 用户明确要求项目内 agent 相关 skill 不要散落到 `.adal`、`.codex`、`.agents` 等目录；当前保留在项目根 `skills/`：`skills/ecosystem-primer/SKILL.md` 与 `skills/vegetation-agent-designer/SKILL.md`。
- 植被指数 Agent 继续采用“确定性规则引擎兜底 + LangChain 可选增强 + 指数库 RAG + 默认网络检索 + 用户确认后执行”的安全架构。
- 新增 `backend/app/services/agent_session_store.py`，使用 `VIP_DATABASE_URL` 时自动建表 `vegetation_agent_sessions` 与 `vegetation_agent_events`；数据库不可用时降级为内存事件，便于测试和演示。
- Agent 计划返回 `sessionId` 与 `conversation`；方案生成、确认提交、统计解读都会追加事件。`/api/agent/sessions/{session_id}/events` 可回查会话事件。
- 前端 `AgentDrawer.vue` 主区域已改为会话状态 + 消息时间线 + 方案卡 + 结果建议；模型 provider/base_url/token/model 配置仍在弹窗中，仅本次请求使用，不持久化敏感字段。
- 验证：Ruff 通过；pytest 26 passed；frontend `npm run build` 通过但保留 MapLibre/ECharts 相关大 chunk warning。
