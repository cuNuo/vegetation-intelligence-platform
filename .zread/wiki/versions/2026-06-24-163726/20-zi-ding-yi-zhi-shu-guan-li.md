自定义指数管理是植被指数智能分析平台的核心扩展功能，允许用户通过智能体交互界面动态创建、注册和持久化新的植被指数。该功能突破了内置30种标准指数的限制，使平台能够适应特定的遥感分析需求，同时保持严格的安全校验和数据一致性。

## 系统架构概览

自定义指数管理采用分层架构设计，从用户交互到数据持久化形成完整的闭环。整个系统由前端交互层、API网关层、业务逻辑层、存储层四个主要部分组成。

```mermaid
graph TB
    subgraph "前端交互层"
        A[AgentDrawer.vue<br>智能体面板] --> B[自定义指数表单]
        B --> C[usePlatformApi.ts<br>API客户端]
    end
    
    subgraph "API网关层"
        D[FastAPI路由<br>routes.py] --> E[请求验证<br>schemas.py]
    end
    
    subgraph "业务逻辑层"
        F[agent_tools.py<br>注册与校验] --> G[advanced_analysis.py<br>表达式验证]
        F --> H[custom_index_store.py<br>持久化管理]
    end
    
    subgraph "存储层"
        I[PostgreSQL<br>vegetation_custom_indices表]
        J[内存注册表<br>INDEX_REGISTRY]
    end
    
    C --> D
    E --> F
    G --> F
    H --> I
    F --> J
```

**数据流向**：用户在前端填写自定义指数表单 → 通过智能体生成方案时参数传递到后端 → 后端进行表达式安全校验 → 注册到内存注册表 → 持久化到PostgreSQL → 服务重启时自动恢复。

Sources: [backend/app/services/agent_tools.py](backend/app/services/agent_tools.py#L123-L151), [backend/app/services/custom_index_store.py](backend/app/services/custom_index_store.py#L1-L111), [frontend/src/components/AgentDrawer.vue](frontend/src/components/AgentDrawer.vue#L299-L308)

## 核心数据结构

自定义指数的数据结构遵循平台统一的指数元数据规范，确保与内置指数在功能上完全兼容。每个自定义指数包含以下核心字段：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 指数唯一标识符，最多40字符，自动转为小写 |
| `name` | string | 是 | 指数显示名称，最多100字符 |
| `expression` | string | 是 | 数学表达式，支持波段引用和标准函数 |
| `description` | string | 否 | 指数用途说明，最多500字符 |
| `expectedRange` | tuple[float, float] | 否 | 预期值域范围，如 `(-1, 1)` |
| `categories` | list[str] | 否 | 分类标签，默认为 `["custom"]` |
| `recommendationTags` | list[str] | 否 | 推荐标签，用于智能体检索 |
| `limitations` | list[str] | 否 | 使用限制说明 |

**表达式语法规则**：
- **允许的波段**：`blue`, `green`, `red`, `red_edge`, `nir`, `swir1`, `swir2`
- **允许的函数**：`abs()`, `sqrt()`, `minimum()`, `maximum()`, `safe_divide()`
- **允许的运算符**：`+`, `-`, `*`, `/`, `**`, 一元负号
- **禁止的结构**：属性访问、下标、lambda、字典、列表、元组、比较、布尔逻辑

**示例表达式**：
```python
# 归一化差异指数
(nir - red) / (nir + red)

# 增强植被指数变体
2.5 * (nir - red) / (nir + 2.4 * red + 1)

# 使用安全除法
safe_divide(nir - red, nir + red)
```

Sources: [backend/app/api/schemas.py](backend/app/api/schemas.py#L66-L80), [backend/app/services/advanced_analysis.py](backend/app/services/advanced_analysis.py#L11-L21)

## 后端实现细节

### 1. 持久化存储层

自定义指数持久化通过 `custom_index_store.py` 实现，采用PostgreSQL作为主存储，内存作为降级方案。

**数据库表结构**：
```sql
CREATE TABLE IF NOT EXISTS vegetation_custom_indices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    expression TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    expected_range JSONB,
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendation_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

**关键特性**：
- **自动建表**：应用启动时通过 `CREATE TABLE IF NOT EXISTS` 自动创建表结构
- **JSONB存储**：使用JSONB类型存储数组和对象字段，保持查询灵活性
- **参数化查询**：所有SQL操作使用参数化查询，防止SQL注入
- **降级策略**：数据库不可用时自动降级为内存模式，保证服务可用性

Sources: [backend/app/services/custom_index_store.py](backend/app/services/custom_index_store.py#L12-L24), [backend/app/services/custom_index_store.py](backend/app/services/custom_index_store.py#L46-L82)

### 2. 注册与校验逻辑

自定义指数注册通过 `agent_tools.py` 中的 `register_custom_index` 函数实现，该函数执行完整的校验流程：

```mermaid
flowchart TD
    A[接收指数规范] --> B[标准化指数ID]
    B --> C{ID有效性检查}
    C -->|无效| D[抛出异常]
    C -->|有效| E{ID是否已存在?}
    E -->|是| D
    E -->|否| F[表达式语法验证]
    F --> G[AST白名单校验]
    G --> H[提取必需波段]
    H --> I[探针测试]
    I --> J[构建IndexDefinition]
    J --> K[注册到INDEX_REGISTRY]
    K --> L[持久化到PostgreSQL]
    L --> M[返回注册结果]
```

**校验步骤详解**：

1. **ID标准化**：将输入ID转为小写，移除非法字符，限制长度为40字符
2. **表达式验证**：使用AST解析器验证表达式语法，确保只包含允许的函数和运算符
3. **波段提取**：从表达式中自动提取所有引用的波段名称
4. **探针测试**：使用示例数据测试表达式，确保返回有效数组
5. **注册到内存**：创建 `IndexDefinition` 对象并添加到全局注册表
6. **持久化存储**：将指数元数据保存到PostgreSQL数据库

**安全性保障**：
- **AST白名单**：只允许安全的数学运算和函数调用
- **空builtins环境**：表达式在 `{"__builtins__": {}}` 环境中执行，防止代码注入
- **类型检查**：验证返回结果必须是有限数组

Sources: [backend/app/services/agent_tools.py](backend/app/services/agent_tools.py#L123-L183), [backend/app/services/agent_tools.py](backend/app/services/agent_tools.py#L249-L254)

### 3. 服务重启恢复

平台在启动时自动从数据库恢复自定义指数，确保数据持久性：

```python
def load_persisted_custom_indices() -> int:
    loaded = 0
    for spec in load_custom_indices():
        try:
            _register_custom_index_in_memory(spec, allow_replace=True)
            loaded += 1
        except ValueError:
            continue
    return loaded
```

**恢复流程**：
1. FastAPI应用启动时调用 `load_persisted_custom_indices()`
2. 从PostgreSQL加载所有自定义指数记录
3. 逐个重新注册到内存注册表（`allow_replace=True` 允许覆盖）
4. 更新系统能力报告中的自定义指数计数

Sources: [backend/app/services/agent_tools.py](backend/app/services/agent_tools.py#L142-L151)

## 前端交互设计

### 1. 智能体集成界面

自定义指数表单集成在智能体面板中，用户可以在生成分析方案的同时创建新指数：

**UI组件结构**：
```vue
<label class="switch-row custom-toggle">
  <input v-model="customIndexEnabled" type="checkbox" />
  同时新建自定义指数
</label>
<div v-if="customIndexEnabled" class="custom-index-box">
  <input v-model="customIndex.id" placeholder="指数ID，如 nd_custom" />
  <input v-model="customIndex.name" placeholder="指数名称" />
  <textarea v-model="customIndex.expression" rows="2" />
  <input v-model="customIndex.description" placeholder="适用场景说明" />
</div>
```

**交互特性**：
- **条件显示**：通过复选框控制自定义指数表单的显示/隐藏
- **实时预览**：表达式输入框支持多行文本，便于查看复杂公式
- **默认值**：提供合理的默认值（如 `(nir - red) / (nir + red)`）降低使用门槛
- **会话集成**：自定义指数作为智能体方案的一部分提交

Sources: [frontend/src/components/AgentDrawer.vue](frontend/src/components/AgentDrawer.vue#L299-L308), [frontend/src/components/AgentDrawer.vue](frontend/src/components/AgentDrawer.vue#L148-L166)

### 2. 类型定义与API调用

前端类型系统严格定义了自定义指数的数据结构：

```typescript
// 自定义指数草稿（前端使用）
export interface AgentCustomIndexDraft {
  id: string
  name: string
  expression: string
  description: string
}

// 指数元数据（完整结构）
export interface IndexMetadata {
  id: string
  name: string
  formula: string
  requiredBands: string[]
  description: string
  expectedRange: [number, number] | null
  parameters: Record<string, number>
  categories: string[]
  recommendationTags: string[]
  limitations: string[]
}
```

**API调用流程**：
```typescript
// 创建智能体方案时传递自定义指数
const plan = await api.createPlan(prompt.value, store.asset.availableBands, {
  llm: currentLlmConfig(),
  enableWebSearch: enableWebSearch.value,
  customIndex: customIndexEnabled.value ? { ...customIndex } : null,
  sessionId: store.activePlan?.sessionId,
})
```

Sources: [frontend/src/types/platform.ts](frontend/src/types/platform.ts#L82-L87), [frontend/src/types/platform.ts](frontend/src/types/platform.ts#L23-L34), [frontend/src/composables/usePlatformApi.ts](frontend/src/composables/usePlatformApi.ts#L80-L106)

## API接口规范

### 1. 创建自定义指数端点

**端点**：`POST /api/indices/custom`

**请求体**（`AgentCustomIndexRequest`）：
```json
{
  "id": "custom_nd",
  "name": "自定义归一化差异指数",
  "expression": "(nir - red) / (nir + red)",
  "description": "用于演示运行期新增指数",
  "expectedRange": [-1, 1],
  "categories": ["custom", "vegetation"],
  "recommendationTags": ["自定义指数", "演示"],
  "limitations": ["云、阴影和积雪会影响结果"]
}
```

**响应**：
```json
{
  "id": "custom_nd",
  "name": "自定义归一化差异指数",
  "formula": "(nir - red) / (nir + red)",
  "requiredBands": ["nir", "red"],
  "description": "用于演示运行期新增指数",
  "expectedRange": [-1, 1],
  "parameters": {},
  "categories": ["custom", "vegetation"],
  "recommendationTags": ["自定义指数", "演示"],
  "limitations": ["云、阴影和积雪会影响结果"],
  "storage": "postgresql"
}
```

**错误响应**：
- `422 Unprocessable Entity`：表达式语法错误、ID已存在、缺少必需波段等

Sources: [backend/app/api/routes.py](backend/app/api/routes.py#L285-L291), [backend/app/api/schemas.py](backend/app/api/schemas.py#L66-L80)

### 2. 系统能力查询

**端点**：`GET /api/system/capabilities`

**相关字段**：
```json
{
  "indexCount": 30,
  "totalIndexCount": 35,
  "customIndexCount": 5,
  "customIndexStorage": "postgresql"
}
```

**说明**：
- `indexCount`：内置标准指数数量（固定30）
- `totalIndexCount`：总指数数量（内置 + 自定义）
- `customIndexCount`：自定义指数数量
- `customIndexStorage`：存储后端类型（`postgresql` 或 `memory`）

Sources: [backend/app/api/routes.py](backend/app/api/routes.py#L353-L368)

## 智能体工作流集成

自定义指数与智能体分析流程深度集成，形成完整的分析闭环：

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as 智能体
    participant R as 注册表
    participant P as PostgreSQL
    
    U->>A: 描述分析需求 + 自定义指数表单
    A->>A: 检索指数库 + RAG
    A->>R: 校验并注册自定义指数
    R->>P: 持久化存储
    R-->>A: 返回注册结果
    A->>A: 生成分析方案
    A->>U: 展示方案（含自定义指数）
    U->>A: 确认执行
    A->>R: 提取所有可用指数
    R->>R: 包含自定义指数
    A->>A: 提交计算任务
```

**集成特性**：
1. **方案生成时注册**：自定义指数在智能体生成方案时即时注册
2. **立即可用**：注册后的自定义指数可立即用于当前和后续的计算任务
3. **智能推荐**：智能体会将自定义指数纳入推荐列表，根据波段可用性判断可执行性
4. **会话持久化**：自定义指数作为会话事件记录，支持会话恢复

Sources: [backend/app/services/agent_tools.py](backend/app/services/agent_tools.py#L186-L199), [backend/app/api/routes.py](backend/app/api/routes.py#L198-L210)

## 配置与部署

### 1. 数据库配置

自定义指数持久化需要配置PostgreSQL连接：

**环境变量**：
```bash
# backend/.env
VIP_DATABASE_URL=postgres://username:password@localhost:5432/vegetation_intelligence
```

**配置选项**：
- **启用持久化**：设置 `VIP_DATABASE_URL` 环境变量
- **禁用持久化**：不设置或留空，自动降级为内存模式
- **数据库要求**：PostgreSQL 12+，需要 `CREATE TABLE` 权限

Sources: [backend/app/settings.py](backend/app/settings.py#L13), [.evidence/active/20260623-1026-PostgreSQL自定义指数持久化.md](.evidence/active/20260623-1026-PostgreSQL自定义指数持久化.md#L1-L52)

### 2. 自动迁移策略

当前采用应用层自动迁移策略，而非传统的数据库迁移工具：

**优势**：
- **零配置部署**：无需运行额外的迁移命令
- **版本兼容**：表结构变更通过 `CREATE TABLE IF NOT EXISTS` 自动处理
- **开发友好**：新开发者克隆代码后直接运行即可

**限制**：
- 不支持复杂的表结构变更（如列类型修改）
- 不支持数据迁移脚本
- 团队协作时需要手动同步表结构变更

**建议**：生产环境考虑引入Alembic进行正式的数据库迁移管理。

Sources: [.evidence/active/20260623-1026-PostgreSQL自定义指数持久化.md](.evidence/active/20260623-1026-PostgreSQL自定义指数持久化.md#L48-L52)

## 监控与诊断

### 1. 系统状态监控

通过系统能力接口监控自定义指数状态：

```bash
# 查询系统能力
curl http://localhost:8000/api/system/capabilities

# 响应示例
{
  "customIndexCount": 5,
  "customIndexStorage": "postgresql"
}
```

### 2. 日志诊断

关键日志点：
- **注册成功**：`自定义指数 custom_nd 已注册到内存注册表`
- **注册失败**：`自定义指数注册失败: 表达式包含未允许名称: invalid_func`
- **数据库连接**：`自定义指数数据库初始化失败: connection refused`
- **恢复统计**：`已从数据库恢复 3 个自定义指数`

### 3. 测试验证

运行相关测试套件验证功能完整性：

```bash
# 后端测试
cd backend
python -m pytest tests/test_indices.py -v

# 前端构建验证
cd frontend
npm run build
```

Sources: [backend/tests/test_indices.py](backend/tests/test_indices.py#L1-L51), [.evidence/active/20260623-1035-任务书覆盖完善.md](.evidence/active/20260623-1035-任务书覆盖完善.md#L30-L38)

## 最佳实践与示例

### 1. 创建实用的自定义指数

**示例1：改进的归一化差异指数**
```json
{
  "id": "ndi_improved",
  "name": "改进归一化差异指数",
  "expression": "(nir - red) / (nir + red + 0.1)",
  "description": "通过添加小常数避免分母为零，提高数值稳定性",
  "expectedRange": [-1, 1],
  "categories": ["custom", "vegetation"],
  "recommendationTags": ["数值稳定", "通用植被"],
  "limitations": ["常数0.1需根据具体数据调整"]
}
```

**示例2：红边叶绿素指数变体**
```json
{
  "id": "reci_modified",
  "name": "修正红边叶绿素指数",
  "expression": "(nir - red_edge) / (nir + red_edge) * 1.5",
  "description": "对标准红边指数进行缩放，增强叶绿素敏感度",
  "expectedRange": [-1.5, 1.5],
  "categories": ["custom", "chlorophyll", "red-edge"],
  "recommendationTags": ["叶绿素", "作物胁迫", "红边波段"],
  "limitations": ["传感器必须具有红边波段", "缩放因子1.5需根据作物类型调整"]
}
```

### 2. 智能体交互示例

**用户输入**：
```
我想分析这片农田的作物健康状况，同时创建一个新的自定义指数来更好地检测早期胁迫。
```

**智能体响应**：
1. 检索相关指数知识（NDVI、NDRE、红边指数等）
2. 根据用户需求推荐现有指数
3. 创建自定义指数：
   ```json
   {
     "id": "early_stress_index",
     "name": "早期胁迫检测指数",
     "expression": "(nir - red_edge) / (nir + red_edge) * (nir / red)",
     "description": "结合红边归一化和近红外/红光比值，增强早期胁迫敏感度"
   }
   ```
4. 生成包含新指数的分析方案
5. 等待用户确认后执行计算

## 故障排查

### 常见问题与解决方案

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 自定义指数创建失败 | 表达式语法错误 | 检查表达式是否符合语法规则，使用 `/api/formulas/validate` 验证 |
| 数据库连接失败 | PostgreSQL服务未启动 | 检查数据库服务状态，验证连接字符串 |
| 服务重启后指数丢失 | 未配置数据库连接 | 设置 `VIP_DATABASE_URL` 环境变量 |
| 指数计算结果异常 | 表达式逻辑错误 | 使用探针测试验证表达式，检查波段映射 |
| 前端表单不显示 | 智能体面板未展开 | 点击"配置模型"按钮展开智能体面板 |

### 调试命令

```bash
# 验证数据库连接
python -c "import psycopg; psycopg.connect('$VIP_DATABASE_URL')"

# 检查指数注册表状态
curl http://localhost:8000/api/indices | jq '.total'

# 验证自定义表达式
curl -X POST http://localhost:8000/api/formulas/validate \
  -H "Content-Type: application/json" \
  -d '{"expression": "(nir - red) / (nir + red)", "allowedBands": ["nir", "red"]}'
```

## 扩展与演进

### 1. 功能增强方向

- **参数化指数**：支持用户定义可调参数（如SAVI中的L参数）
- **指数版本管理**：支持指数定义的版本控制和回滚
- **批量导入/导出**：支持从JSON文件批量导入指数定义
- **指数共享**：支持团队间共享自定义指数库

### 2. 性能优化

- **缓存策略**：对频繁使用的自定义指数进行缓存
- **索引优化**：为PostgreSQL表添加适当的索引
- **查询优化**：优化指数检索和加载逻辑

### 3. 集成扩展

- **pygeoapi插件**：将自定义指数集成到OGC API - Processes
- **Celery任务**：支持异步指数注册和批量处理
- **MinIO存储**：将指数元数据存储到对象存储系统

## 下一步

自定义指数管理是平台扩展能力的核心，建议结合以下相关文档深入理解：

- **指数注册表**：了解内置30种标准指数的定义和分类
- **智能体架构**：理解智能体如何集成自定义指数功能
- **PostgreSQL持久化**：深入了解数据存储和查询优化
- **REST API**：查看完整的API接口文档和示例
- **测试策略**：了解如何验证自定义指数功能的正确性

通过自定义指数管理，平台能够适应不断变化的遥感分析需求，为用户提供灵活、安全、可扩展的指数定义能力。