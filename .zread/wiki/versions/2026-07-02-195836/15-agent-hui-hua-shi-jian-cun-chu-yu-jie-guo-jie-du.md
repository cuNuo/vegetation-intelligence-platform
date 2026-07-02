本页文档详细阐述了植被指数智能分析平台中 **Agent 会话事件存储**与**结果解读**的完整架构。会话事件存储机制确保了用户与智能体的每一次交互都被结构化记录并可按时间线回放；结果解读模块则将统计学数值转换为面向农学决策的语义化建议。两者共同构成了智能体系统"可追溯、可解释"的核心基础设施。

## 会话事件存储架构

智能体系统采用**双层存储策略**：优先使用 PostgreSQL 进行持久化存储，当数据库不可用时自动降级至内存字典。这种设计既保证了生产环境的数据持久性，又确保了开发测试环境的零依赖启动。

`agent_session_store.py` 文件定义了存储层的全部逻辑。每个会话由 `create_session` 函数创建，生成唯一 UUID 作为 `session_id`，该 ID 会贯穿整个交互生命周期。事件通过 `append_event` 函数追加，每条事件包含角色（user/assistant）、事件类型（question/plan/execution/interpretation）、文本内容和结构化载荷。`list_events` 函数按 `created_at` 时间戳升序返回事件序列，供前端渲染对话时间线。

数据库模式包含两张关联表：`vegetation_agent_sessions` 存储会话元数据（标题、创建时间、更新时间），`vegetation_agent_events` 存储事件详情并通过外键 `session_id` 与会话关联，支持级联删除。事件表的 `payload` 字段使用 JSONB 类型，可存储任意结构化的上下文信息，如可用波段列表、引擎选择、警告信息等。

Sources: [agent_session_store.py](backend/app/services/agent_session_store.py#L1-L158)

## 事件类型与生命周期

Agent 会话事件覆盖了智能体交互的完整生命周期，共定义了四种核心事件类型：

| 事件类型 | 触发时机 | 载荷内容 | 典型场景 |
|---------|---------|---------|---------|
| `question` | 用户提交分析请求时 | `availableBands`、`rasterWidth`、`rasterHeight` | 用户输入"分析这片农田的长势" |
| `plan` | 方案生成完成时 | `planId`、`intent`、`selectedIndices`、`engine`、`trace`、`warnings` | 返回包含 NDVI、EVI、GNDVI 的执行方案 |
| `execution` | 确认执行提交时 | `planId`、`jobId`、`executionSheet`、`trace` | 用户确认后提交异步计算任务 |
| `interpretation` | 统计解读完成时 | `trace`、`llmStatus`、`insightCount` | 基于统计均值生成农学建议 |

每种事件类型都携带 `trace` 数组，记录智能体的推理步骤，包括"接收问题"、"RAG检索指数知识"、"网络检索适用场景"、"推荐指数"、"选择执行引擎"等阶段。这种设计使得前端可以展示透明的思考过程，增强用户对智能体决策的信任感。

Sources: [agent.py](backend/app/services/agent.py#L130-L160), [agent.py](backend/app/services/agent.py#L260-L280)

## 结果解读的核心流程

结果解读遵循**规则优先、LLM 增强**的设计原则。`interpret_products` 函数首先基于内置规则库对每个产品的统计信息进行结构化解读，然后 `interpret_results` 方法可选地调用 LangChain 进行语义增强。

规则库针对不同指数族定义了差异化的阈值体系。对于 NDVI、EVI、GNDVI 等植被活力指数，均值低于 0.25 标记为 `danger` 级别（需排查裸土、缺苗或病虫害），0.25-0.55 为 `warning` 级别（建议结合历史同期判断），高于 0.55 为 `normal` 级别（整体长势较好）。对于 NDMI、MSI 等水分指数，负值标记为 `warning`。此外，规则还会分析标准差以评估空间差异程度。

LLM 增强阶段通过 `_invoke_langchain` 方法调用配置的 LLM 服务（支持 OpenAI 兼容和 Anthropic 两种提供商），将统计摘要和用户目标发送给模型，请求生成 `summary`（总述）和 `nextActions`（后续建议）。当 LLM 不可用时（未配置或调用失败），系统自动降级至纯规则解读，确保服务连续性。

Sources: [agent_tools.py](backend/app/services/agent_tools.py#L310-L370), [agent.py](backend/app/services/agent.py#L400-L460)

## 前端会话时间线渲染

前端 `AgentDrawer.vue` 组件负责渲染完整的对话时间线。会话事件通过 `conversationEvents` 计算属性聚合，该属性优先使用后端返回的持久化事件（来自 `interpretation.value.conversation` 或 `store.activePlan.conversation`），同时合并本地未持久化的消息。

为优化用户体验，组件实现了**思考步骤队列**机制。SSE 流式返回的思考事件不会立即渲染，而是先进入 `thinkingQueue`，然后按 `THINKING_STEP_DELAY_MS`（1180ms）间隔逐步释放，避免界面瞬时跳动。每个思考步骤会经历"running → done"的状态转换，转换前保留 `THINKING_MIN_DWELL_MS`（760ms）的最小停留时间。

事件类型到显示标题的映射通过 `eventTitle` 函数完成：`question` 映射为"用户问题"，`plan` 映射为"方案生成"，`execution` 映射为"任务执行"，`interpretation` 映射为"统计解读"。这种语义化映射使得非技术用户也能理解对话流程。

Sources: [AgentDrawer.vue](frontend/src/components/AgentDrawer.vue#L1-L200), [AgentDrawer.vue](frontend/src/components/AgentDrawer.vue#L200-L400)

## API 接口契约

平台通过两个 REST 端点暴露会话事件和结果解读能力：

**获取会话事件**：`GET /api/agent/sessions/{session_id}/events` 返回指定会话的全部事件列表，响应结构为 `{"items": [AgentConversationEvent, ...]}`。每个事件对象包含 `id`、`role`、`eventType`、`content`、`payload` 和 `createdAt` 字段。

**结果解读**：`POST /api/agent/interpret-results` 接收产品统计信息数组、用户目标描述、可选 LLM 配置和会话 ID，返回结构化的解读结果。响应包含 `summary`（总述）、`insights`（洞察数组，每条包含标题、严重级别和详情）、`nextActions`（后续建议数组）以及 `conversation`（包含本次解读事件的完整会话序列）。

前端通过 `usePlatformApi` composable 封装了这两个接口：`interpretResults` 方法负责调用结果解读端点并处理响应，`getAgentSessionEvents` 方法（通过 `VegetationAgent.get_session_events` 间接调用）负责获取会话事件。

Sources: [routes.py](backend/app/api/routes.py#L470-L480), [routes.py](backend/app/api/routes.py#L500-L510)

## 存储降级策略

会话存储实现了优雅的降级策略。当 PostgreSQL 不可用时（数据库连接失败或未配置 `database_url`），系统自动切换至内存字典存储。`is_enabled` 函数检查数据库配置状态，`initialize_agent_session_store` 函数尝试创建表结构，失败时返回 `False` 并记录警告日志。

内存降级模式下，会话存储在 `_MEMORY_SESSIONS` 字典中，事件存储在 `_MEMORY_EVENTS` 字典中。虽然内存存储不提供持久化保证，但完整保留了会话的读写逻辑，确保开发测试环境的功能一致性。系统能力端点 `GET /api/system/capabilities` 会返回 `agentSessionStorage` 字段，明确指示当前存储后端类型。

Sources: [agent_session_store.py](backend/app/services/agent_session_store.py#L20-L50), [routes.py](backend/app/api/routes.py#L600-L610)

## 结果解读的洞察结构

解读结果中的 `insights` 数组是连接统计数值与农学决策的关键桥梁。每条洞察包含三个核心字段：

- **title**：格式为"指数名 均值 数值"，如"NDVI 均值 0.320"
- **severity**：严重级别，取值为 `normal`（正常）、`warning`（需关注）或 `danger`（需优先处理）
- **detail**：具体的农学解释，包含标准差分析和空间差异评估

当产品缺少有效统计时（如像元全部为 nodata），系统会生成 `warning` 级别的洞察，提示用户检查波段映射、裁剪范围和 nodata 掩膜。`summary` 字段根据洞察中最高严重级别动态生成：存在 `danger` 时提示"需要优先核查的低值或异常区域"，存在 `warning` 时提示"仍存在需要结合外部资料复核的信号"，全部 `normal` 时提示"可作为当前地块状态的基线参考"。

Sources: [agent_tools.py](backend/app/services/agent_tools.py#L350-L370), [agent_tools.py](frontend/src/components/AgentDrawer.vue#L300-L350)

## 跨会话知识隔离

会话事件存储与知识库存储通过 `session_id` 实现松耦合关联。`agent_knowledge_store.py` 中的知识文档表包含可选的 `session_id` 字段，允许将导入的外部知识限定于特定会话上下文。

然而，知识检索逻辑（`search_persisted_knowledge`）采用全库扫描策略，不按会话隔离。这种设计基于"知识应全局共享"的原则：用户在一次会话中导入的指数说明文档，在后续会话中仍可被 RAG 检索召回。安全约束通过 `SPECIFIC_DIAGNOSIS_TERMS` 黑名单实现，防止知识文档中的特定病害诊断术语被未提及该病害的查询意外召回。