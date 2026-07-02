本文档聚焦平台在**运行期**新增自定义植被指数的全链路机制：从 API 接收、AST 安全校验、内存注册、PostgreSQL 持久化，到服务重启后自动恢复。该机制确保用户或智能体（Agent）在不修改源码的前提下安全扩展指数库。

Sources: [custom_index_store.py](backend/app/services/custom_index_store.py#L1-L121), [agent_tools.py](backend/app/services/agent_tools.py#L238-L280)

## 设计目标与约束

自定义指数注册遵循三个核心约束：**安全优先**（AST 白名单校验，禁止任意代码执行）、**降级透明**（数据库不可用时退化内存存储并向前端公开存储模式）、**无源码侵入**（运行期动态追加至 `INDEX_REGISTRY`，不修改 `indices.py` 内的 35 个内置定义）。该设计使得智能体（Agent）在对话中即可引入新指数，而无需开发者重新部署。

Sources: [agent_tools.py](backend/app/services/agent_tools.py#L238-L280), [SKILL.md](skills/vegetation-agent-designer/SKILL.md#L37-L41)

## 整体数据流

自定义指数从提交到生效经历五步流水线。请求可来自两条路径：智能体对话（`POST /api/agent/plan` 中携带 `customIndex` 字段）或直接 REST 调用（`POST /api/indices/custom`）。两条路径最终汇聚到 `register_custom_index` 函数。

```mermaid
flowchart TD
    A["用户 / Agent 提交指数定义"] --> B["Pydantic Schema 校验"]
    B --> C["AST 白名单校验"]
    C --> D["波段推断 + 探针试算"]
    D --> E["注册到 INDEX_REGISTRY"]
    E --> F["PostgreSQL UPSERT"]
    F --> G{"数据库可用?"}
    G -->|是| H["storage = postgresql"]
    G -->|否| I["storage = memory"]
    H --> J["返回指数元数据"]
    I --> J
```

Sources: [routes.py](backend/app/api/routes.py#L536-L543), [agent_tools.py](backend/app/services/agent_tools.py#L238-L280), [custom_index_store.py](backend/app/services/custom_index_store.py#L47-L77)

## API 层：请求契约

前端或 Agent 提交自定义指数时，请求体须满足 `AgentCustomIndexRequest` 模型。该模型使用 Pydantic v2 的 `Field` 约束长度、别名和默认值，并通过 `populate_by_name` 同时支持驼峰和下划线字段名。

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `id` | `str` | ✅ | 2-40 字符 | 指数唯一标识，自动转小写并去特殊字符 |
| `name` | `str` | ✅ | 2-100 字符 | 显示名称 |
| `expression` | `str` | ✅ | 1-500 字符 | 表达式，仅允许波段名、安全函数和算术运算 |
| `description` | `str` | ❌ | ≤500 字符 | 用途描述 |
| `expectedRange` | `tuple[float, float]` | ❌ | - | 期望值范围 |
| `categories` | `list[str]` | ❌ | ≤8 项，默认 `["custom"]` | 分类标签 |
| `recommendationTags` | `list[str]` | ❌ | ≤8 项 | 推荐场景标签 |
| `limitations` | `list[str]` | ❌ | ≤8 项 | 使用限制 |

Sources: [schemas.py](backend/app/api/schemas.py#L85-L107)

REST 端点 `POST /api/indices/custom` 接收该模型并委托给 `register_custom_index`：

Sources: [routes.py](backend/app/api/routes.py#L536-L543)

## 安全校验：AST 白名单机制

自定义表达式的安全性通过三层校验保障，这是整个机制最关键的安全边界。

**第一层：Pydantic 契约校验** — 拒绝长度超限、类型不匹配的请求体。

**第二层：AST 白名单遍历** — `SafeExpressionValidator` 遍历表达式的抽象语法树，仅允许以下语法元素：

| 允许类别 | 具体项 |
|---------|--------|
| 波段名称 | `blue`, `green`, `red`, `red_edge`, `nir`, `swir1`, `swir2` |
| 数学函数 | `abs`, `sqrt`, `minimum`, `maximum` |
| 算术运算符 | `+`, `-`, `*`, `/`, `**`, 一元 `-` |
| 数字字面量 | 整数和浮点数 |

所有其他语法结构（属性访问、下标、lambda、列表、字典、比较、布尔逻辑）均被拒绝。这确保了表达式无法调用任意 Python 代码。

**第三层：探针试算** — 使用 `np.array([[0.2, 0.6]])` 作为探针数组执行表达式，验证结果为形状 `(1, 2)` 的有限 `float32` 数组。这一步排除了除以零、类型错误等运行期异常。

Sources: [advanced_analysis.py](backend/app/services/advanced_analysis.py#L18-L95), [agent_tools.py](backend/app/services/agent_tools.py#L343-L353)

## 内存注册：动态追加 INDEX_REGISTRY

校验通过后，`_register_custom_index_in_memory` 将解析后的表达式编译为可调用函数（`_build_expression`），并构造完整的 `IndexDefinition` 数据类实例，追加到全局 `INDEX_REGISTRY` 字典。此时该指数即可被所有计算引擎（NumPy、Joblib、PyTorch）和 API 端点识别。

`_build_expression` 函数将标准化后的表达式字符串通过 `ast.parse` + `compile` 编译为字节码，并在执行时注入安全函数映射（`abs→xp.abs`, `sqrt→xp.sqrt`, `safe_divide→safe_divide(xp, ...)`) 和波段数组。这保证了自定义指数与内置指数使用相同的跨引擎计算语义。

Sources: [agent_tools.py](backend/app/services/agent_tools.py#L282-L310), [agent_tools.py](backend/app/services/agent_tools.py#L329-L341)

## PostgreSQL 持久化层

内存注册完成后，`register_custom_index` 随即调用 `save_custom_index` 将指数定义写入 PostgreSQL。持久化层通过 `VIP_DATABASE_URL` 环境变量检测数据库可用性。

### 表结构

`vegetation_custom_indices` 表由应用启动时自动创建（`CREATE TABLE IF NOT EXISTS`），无需 Alembic 迁移：

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `TEXT` | `PRIMARY KEY` | 指数标识 |
| `name` | `TEXT` | `NOT NULL` | 显示名称 |
| `expression` | `TEXT` | `NOT NULL` | 标准化表达式 |
| `description` | `TEXT` | `NOT NULL DEFAULT ''` | 描述 |
| `expected_range` | `JSONB` | - | 值范围，可为 NULL |
| `categories` | `JSONB` | `NOT NULL DEFAULT '[]'` | 分类数组 |
| `recommendation_tags` | `JSONB` | `NOT NULL DEFAULT '[]'` | 推荐标签数组 |
| `limitations` | `JSONB` | `NOT NULL DEFAULT '[]'` | 限制数组 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` | 更新时间 |

Sources: [custom_index_store.py](backend/app/services/custom_index_store.py#L22-L35)

### UPSERT 语义

写入采用 `INSERT ... ON CONFLICT (id) DO UPDATE SET` 模式。当同一 `id` 的指数被再次提交时（例如 Agent 对话中用户修正了表达式），所有字段和 `updated_at` 均被更新。这保证了幂等性：重复提交不会产生重复记录。

Sources: [custom_index_store.py](backend/app/services/custom_index_store.py#L49-L77)

### 降级策略

当 `VIP_DATABASE_URL` 未配置或数据库连接失败时，`save_custom_index` 返回 `False`，调用方将 `storage` 字段标记为 `"memory"`。此时指数仅存在于当前进程的 `INDEX_REGISTRY` 中，服务重启后会丢失。前端通过 `/api/system/capabilities` 端点可查询当前存储模式：

| 字段 | 类型 | 说明 |
|------|------|------|
| `customIndexCount` | `number` | 运行期新增的自定义指数数量 |
| `customIndexStorage` | `"postgresql" \| "memory"` | 当前存储后端 |

Sources: [routes.py](backend/app/api/routes.py#L596-L608), [custom_index_store.py](backend/app/services/custom_index_store.py#L40-L45)

## 启动恢复：自动加载持久化指数

FastAPI 的 `lifespan` 上下文管理器在应用启动时调用 `load_persisted_custom_indices()`。该函数从 PostgreSQL 读取所有已保存的自定义指数，逐条调用 `_register_custom_index_in_memory`（`allow_replace=True`）恢复到 `INDEX_REGISTRY`。此过程在数据库不可用时静默失败，不影响服务启动。

Sources: [main.py](backend/app/main.py#L27-L35), [agent_tools.py](backend/app/services/agent_tools.py#L224-L234)

## 与智能体系统的集成

自定义指数注册是智能体（Agent）工作流中的关键步骤。当用户在对话中描述需要新指数时，Agent 在生成分析方案前会先注册该指数，使其纳入候选推荐列表：

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as Agent (agent.py)
    participant T as agent_tools.py
    participant S as custom_index_store.py
    participant R as INDEX_REGISTRY

    U->>A: "我想用 (nir-red)/(nir+red) 做一个自定义指数"
    A->>T: register_custom_index(spec)
    T->>T: validate_custom_expression (AST白名单)
    T->>T: _probe_expression (探针试算)
    T->>R: INDEX_REGISTRY[id] = definition
    T->>S: save_custom_index(spec)
    S-->>T: True (PostgreSQL写入成功)
    T-->>A: metadata (storage=postgresql)
    A->>A: 将新指数插入候选列表首位
    A-->>U: 生成包含新指数的分析方案
```

在方案生成阶段，Agent 会将自定义指数的 `requiredBands` 合并到 `available_bands` 中，并将其插入候选指数列表的首位，确保用户自定义的需求被优先考虑。

Sources: [agent.py](backend/app/services/agent.py#L120-L150), [agent_tools.py](backend/app/services/agent_tools.py#L238-L280)

## 前端交互

前端 `AgentDrawer.vue` 组件提供自定义指数的表单输入区域。用户可通过开关启用自定义指数，填写 ID、名称、表达式和描述。当 Agent 生成的方案包含自定义指数时，方案详情中会展示该指数的元数据，并在 `/api/system/capabilities` 返回的存储状态中反映持久化情况。

`IndexCatalog.vue` 组件展示所有已注册的指数（包括运行期新增的自定义指数），支持按分类筛选和关键字搜索。自定义指数默认归入 `"custom"` 分类。

Sources: [AgentDrawer.vue](frontend/src/components/AgentDrawer.vue#L55-L62), [IndexCatalog.vue](frontend/src/components/IndexCatalog.vue#L34-L49)

## 配置与环境

自定义指数持久化功能通过单一环境变量控制：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VIP_DATABASE_URL` | `None` | PostgreSQL 连接字符串，格式如 `postgresql://user:pass@host:5432/dbname` |

未配置时，功能自动降级为内存存储。Docker Compose 部署时需在 `api-basic` 等服务的 `environment` 中添加该变量。

Sources: [settings.py](backend/app/settings.py#L22), [compose.yml](compose.yml#L8-L20)

## 已知限制

当前实现有三个值得后续改进的限制：表结构由应用启动时 `CREATE TABLE IF NOT EXISTS` 自举，未接入 Alembic 迁移系统，团队协作时需手动同步表结构变更；自定义指数仅通过 `load_persisted_custom_indices` 在启动时加载，运行期其他实例不会实时感知新增；`_build_expression` 使用 `eval` 执行已校验的表达式，虽然在空 `__builtins__` 环境中运行且仅允许白名单语法，但仍属于需要持续关注的安全边界。