PostgreSQL持久化是植被指数智能分析平台的可选数据存储层，为自定义植被指数、智能体知识库和会话事件提供持久化存储能力。该系统采用**优雅降级**架构设计，在PostgreSQL不可用时自动回退到内存存储，确保平台功能始终可用。系统通过`VIP_DATABASE_URL`环境变量配置数据库连接，支持本地开发和生产部署两种模式。

## 架构概览

PostgreSQL持久化系统采用**模块化存储服务**架构，三个核心存储服务独立运行、独立初始化，但共享同一个数据库连接配置。这种设计既保证了各功能模块的独立性，又避免了数据库连接的重复配置。

```mermaid
graph TB
    subgraph "配置层"
        ENV[".env 配置文件"]
        SETTINGS["Settings 类"]
    end
    
    subgraph "存储服务层"
        CIS["custom_index_store<br/>自定义指数存储"]
        AKS["agent_knowledge_store<br/>知识库存储"]
        ASS["agent_session_store<br/>会话事件存储"]
    end
    
    subgraph "PostgreSQL 数据库"
        TABLE1["vegetation_custom_indices"]
        TABLE2["vegetation_agent_knowledge_documents"]
        TABLE3["vegetation_agent_sessions"]
        TABLE4["vegetation_agent_events"]
    end
    
    subgraph "内存降级层"
        MEMORY1["内存字典存储"]
    end
    
    ENV -->|VIP_DATABASE_URL| SETTINGS
    SETTINGS --> CIS
    SETTINGS --> AKS
    SETTINGS --> ASS
    
    CIS -->|psycopg 连接| TABLE1
    AKS -->|psycopg 连接| TABLE2
    ASS -->|psycopg 连接| TABLE3
    ASS -->|psycopg 连接| TABLE4
    
    CIS -.->|数据库不可用| MEMORY1
    AKS -.->|数据库不可用| MEMORY1
    ASS -.->|数据库不可用| MEMORY1
```

**Sources: [settings.py](backend/app/settings.py#L13), [custom_index_store.py](backend/app/services/custom_index_store.py#L1-L111), [agent_knowledge_store.py](backend/app/services/agent_knowledge_store.py#L1-L162), [agent_session_store.py](backend/app/services/agent_session_store.py#L1-L147)**

## 数据库表结构

系统使用四个核心表存储不同类型的数据，所有表都采用**TIMESTAMPTZ**类型确保时区一致性，并使用**JSONB**类型存储结构化数据以保持灵活性。

### 自定义指数表 (vegetation_custom_indices)

该表存储用户通过智能体创建的自定义植被指数，包含指数定义、公式、分类标签和限制条件等完整信息。

```sql
CREATE TABLE IF NOT EXISTS vegetation_custom_indices (
    id TEXT PRIMARY KEY,                    -- 指数唯一标识符
    name TEXT NOT NULL,                     -- 指数显示名称
    expression TEXT NOT NULL,               -- 数学表达式
    description TEXT NOT NULL DEFAULT '',   -- 指数描述
    expected_range JSONB,                   -- 预期值范围 [min, max]
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,          -- 分类标签
    recommendation_tags JSONB NOT NULL DEFAULT '[]'::jsonb, -- 推荐标签
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,         -- 使用限制
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),          -- 创建时间
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()           -- 更新时间
)
```

**Sources: [custom_index_store.py](backend/app/services/custom_index_store.py#L12-L25)**

### 知识库文档表 (vegetation_agent_knowledge_documents)

该表存储智能体导入的外部知识文档，用于RAG检索增强生成。文档内容被截断到12000字符以控制存储大小。

```sql
CREATE TABLE IF NOT EXISTS vegetation_agent_knowledge_documents (
    id UUID PRIMARY KEY,                    -- 文档唯一标识符
    title TEXT NOT NULL,                    -- 文档标题
    content TEXT NOT NULL,                  -- 文档内容
    source TEXT NOT NULL DEFAULT 'user-upload', -- 来源标识
    session_id UUID,                        -- 关联会话ID
    created_at TIMESTAMPTZ NOT NULL DEFAULT now() -- 创建时间
)
```

**Sources: [agent_knowledge_store.py](backend/app/services/agent_knowledge_store.py#L15-L24)**

### 会话与事件表

系统使用两个关联表存储智能体会话信息，采用**外键约束**和**级联删除**确保数据一致性。

```sql
-- 会话主表
CREATE TABLE IF NOT EXISTS vegetation_agent_sessions (
    id UUID PRIMARY KEY,                    -- 会话唯一标识符
    title TEXT NOT NULL DEFAULT '',         -- 会话标题
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), -- 创建时间
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()  -- 最后更新时间
)

-- 会话事件表
CREATE TABLE IF NOT EXISTS vegetation_agent_events (
    id UUID PRIMARY KEY,                    -- 事件唯一标识符
    session_id UUID NOT NULL REFERENCES vegetation_agent_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                     -- 角色 (user/assistant/system)
    event_type TEXT NOT NULL,               -- 事件类型 (question/plan/confirm等)
    content TEXT NOT NULL DEFAULT '',       -- 事件内容
    payload JSONB NOT NULL DEFAULT '{}'::jsonb, -- 附加数据
    created_at TIMESTAMPTZ NOT NULL DEFAULT now() -- 创建时间
)
```

**Sources: [agent_session_store.py](backend/app/services/agent_session_store.py#L15-L34)**

## 配置与初始化

### 环境变量配置

PostgreSQL连接通过`VIP_DATABASE_URL`环境变量配置，支持标准PostgreSQL连接字符串格式。系统在`.env.example`中提供了配置示例。

```env
# 可选：PostgreSQL，用于持久化自定义植被指数。
VIP_DATABASE_URL=postgresql://postgres:change-me@127.0.0.1:5432/vegetation_intelligence
```

**Sources: [.env.example](.env.example#L9-L10), [settings.py](backend/app/settings.py#L13)**

### 启动时初始化

系统采用**懒初始化**模式，各存储服务在首次使用时自动检查数据库连接并初始化表结构。FastAPI应用在lifespan启动阶段调用`load_persisted_custom_indices()`恢复已保存的自定义指数。

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ... 其他初始化 ...
    load_persisted_custom_indices()  # 恢复PostgreSQL中的自定义指数
    # ... 其他初始化 ...
```

**Sources: [main.py](backend/app/main.py#L18-L27), [agent_tools.py](backend/app/services/agent_tools.py#L142-L150)**

### 存储状态查询

系统通过`/api/system/capabilities`接口提供存储状态信息，前端可据此显示当前存储模式。

```python
@router.get("/api/system/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        # ... 其他能力 ...
        "customIndexStorage": "postgresql" if is_enabled() else "memory",
        "agentSessionStorage": "postgresql" if is_agent_session_store_enabled() else "memory",
        "agentKnowledgeStorage": "postgresql" if is_agent_knowledge_store_enabled() else "memory",
    }
```

**Sources: [routes.py](backend/app/api/routes.py#L353-L368)**

## 数据操作接口

### 自定义指数存储

自定义指数存储服务提供完整的CRUD操作，支持**UPSERT**语义避免重复插入，并自动更新修改时间戳。

```python
def save_custom_index(spec: dict[str, Any]) -> bool:
    """保存自定义指数到PostgreSQL，支持更新已存在记录"""
    sql = """
    INSERT INTO vegetation_custom_indices (...)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        expression = EXCLUDED.expression,
        -- ... 其他字段 ...
        updated_at = now()
    """
    # ... 执行SQL ...

def load_custom_indices() -> list[dict[str, Any]]:
    """加载所有自定义指数，按更新时间倒序排列"""
    sql = """
    SELECT id, name, expression, description, expected_range,
           categories, recommendation_tags, limitations
    FROM vegetation_custom_indices
    ORDER BY updated_at DESC
    """
    # ... 执行SQL并转换结果 ...
```

**Sources: [custom_index_store.py](backend/app/services/custom_index_store.py#L46-L110)**

### 知识库存储

知识库存储服务支持文档导入和全文检索，检索算法采用**词频匹配**策略，结合中文专业术语词典提高检索准确性。

```python
def save_knowledge_document(spec: dict[str, Any]) -> dict[str, Any]:
    """保存知识文档，同时更新内存缓存"""
    document = {
        "id": str(uuid.uuid4()),
        "title": str(spec.get("title") or "外部指数知识").strip()[:200],
        "content": content[:12000],  # 内容截断控制
        "source": str(spec.get("source") or "user-upload").strip()[:500],
        "sessionId": spec.get("sessionId"),
    }
    _MEMORY_DOCUMENTS[document["id"]] = document  # 内存缓存
    # ... 数据库写入 ...

def search_persisted_knowledge(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """在持久化知识库中进行全文检索"""
    terms = _tokenize(query)  # 分词处理
    # ... 检索和评分逻辑 ...
```

**Sources: [agent_knowledge_store.py](backend/app/services/agent_knowledge_store.py#L45-L161)**

### 会话事件存储

会话事件存储服务维护会话生命周期，支持事件追加和查询，并自动更新会话的最后活动时间。

```python
def create_session(title: str) -> str:
    """创建新会话，返回会话ID"""
    session_id = str(uuid.uuid4())
    # ... 内存和数据库存储 ...

def append_event(session_id: str, role: str, event_type: str, 
                 content: str, payload: dict[str, Any] | None = None) -> bool:
    """向会话追加事件，自动更新会话时间戳"""
    # ... 事件存储逻辑 ...
    connection.execute(
        "UPDATE vegetation_agent_sessions SET updated_at = now() WHERE id = %s",
        (session_id,),
    )

def list_events(session_id: str) -> list[dict[str, Any]]:
    """获取会话的所有事件，按时间正序排列"""
    # ... 事件查询逻辑 ...
```

**Sources: [agent_session_store.py](backend/app/services/agent_session_store.py#L56-L146)**

## 降级策略与容错机制

系统采用**优雅降级**设计，当PostgreSQL不可用时自动回退到内存存储，确保平台核心功能不受影响。这种设计特别适合开发环境和网络不稳定的场景。

### 降级触发条件

```python
def is_enabled() -> bool:
    """检查PostgreSQL是否可用"""
    return bool(settings.database_url)

def initialize_custom_index_store() -> bool:
    """尝试初始化数据库，失败时返回False触发降级"""
    if not settings.database_url:
        return False
    try:
        import psycopg
        with psycopg.connect(settings.database_url) as connection:
            connection.execute(CREATE_TABLE_SQL)
        return True
    except Exception as error:  # noqa: BLE001 - 数据库不可用时降级内存
        LOGGER.warning("自定义指数数据库初始化失败: %s", error)
        return False
```

**Sources: [custom_index_store.py](backend/app/services/custom_index_store.py#L28-L43)**

### 内存降级实现

每个存储服务都维护独立的内存字典作为降级存储：

```python
# agent_knowledge_store.py 中的内存降级
_MEMORY_DOCUMENTS: dict[str, dict[str, Any]] = {}

def save_knowledge_document(spec: dict[str, Any]) -> dict[str, Any]:
    # ... 创建文档对象 ...
    _MEMORY_DOCUMENTS[document["id"]] = document  # 始终更新内存缓存
    if not initialize_knowledge_store():
        document["storage"] = "memory"  # 标记存储模式
        return document
    # ... 数据库写入 ...
    document["storage"] = "postgresql"
    return document
```

**Sources: [agent_knowledge_store.py](backend/app/services/agent_knowledge_store.py#L13, L56-L60)**

## 集成点与使用场景

### 智能体工具集成

PostgreSQL持久化与智能体工具深度集成，支持自定义指数的注册、加载和检索。

```python
# agent_tools.py 中的集成示例
from app.services.custom_index_store import load_custom_indices, save_custom_index

def register_custom_index(spec: dict[str, Any]) -> dict[str, Any]:
    """注册自定义指数，同时保存到PostgreSQL"""
    metadata = _register_custom_index_in_memory(spec, allow_replace=False)
    persisted = save_custom_index({...})  # 持久化到数据库
    metadata["storage"] = "postgresql" if persisted else "memory"
    return metadata

def load_persisted_custom_indices() -> int:
    """从PostgreSQL加载已保存的自定义指数"""
    loaded = 0
    for spec in load_custom_indices():
        try:
            _register_custom_index_in_memory(spec, allow_replace=True)
            loaded += 1
        except ValueError:
            continue
    return loaded
```

**Sources: [agent_tools.py](backend/app/services/agent_tools.py#L18, L123-L150)**

### API端点暴露

系统通过REST API暴露存储状态和操作接口：

```python
# 自定义指数创建端点
@router.post("/api/indices/custom", status_code=status.HTTP_201_CREATED)
def create_custom_index(request: AgentCustomIndexRequest) -> dict[str, Any]:
    try:
        return register_custom_index(request.model_dump(by_alias=True))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

# 知识库导入端点
@router.post("/api/agent/knowledge", status_code=status.HTTP_201_CREATED)
def import_agent_knowledge(request: AgentKnowledgeImportRequest) -> dict[str, Any]:
    try:
        document = save_knowledge_document(request.model_dump(by_alias=True))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return document
```

**Sources: [routes.py](backend/app/api/routes.py#L276-L291)**

## 部署与运维

### Docker Compose配置

虽然compose.yml中没有直接包含PostgreSQL服务，但系统支持通过环境变量连接外部PostgreSQL实例。

```yaml
# 在compose.yml的api-environment中可以添加
x-api-environment: &api-environment
  # ... 其他环境变量 ...
  # VIP_DATABASE_URL: postgres://user:pass@postgres:5432/vegetation_intelligence
```

**Sources: [compose.yml](compose.yml#L3-L10)**

### 依赖管理

系统使用`psycopg[binary]`作为PostgreSQL驱动，提供二进制编译版本以简化安装：

```toml
# pyproject.toml 中的依赖声明
dependencies = [
  # ... 其他依赖 ...
  "psycopg[binary]>=3.2,<4",  # PostgreSQL驱动
  # ... 其他依赖 ...
]
```

**Sources: [pyproject.toml](backend/pyproject.toml#L22)**

### 监控与日志

系统记录数据库操作异常，便于运维监控：

```python
LOGGER.warning("自定义指数数据库初始化失败: %s", error)
LOGGER.warning("Agent知识库数据库初始化失败: %s", error)
LOGGER.warning("Agent会话数据库初始化失败: %s", error)
```

**Sources: [custom_index_store.py](backend/app/services/custom_index_store.py#L42), [agent_knowledge_store.py](backend/app/services/agent_knowledge_store.py#L41), [agent_session_store.py](backend/app/services/agent_session_store.py#L52)**

## 最佳实践与注意事项

### 连接字符串格式

PostgreSQL连接字符串支持标准格式，建议使用URL编码处理特殊字符：

```
postgresql://username:password@host:port/database?options
```

**Sources: [.env.example](.env.example#L10)**

### 数据迁移考虑

当前系统使用`CREATE TABLE IF NOT EXISTS`进行表初始化，适合开发和原型阶段。生产环境建议：

1. **使用Alembic进行数据库迁移**
2. **避免直接修改表结构**
3. **定期备份数据库**

**Sources: [.evidence/active/20260623-1026-PostgreSQL自定义指数持久化.md](.evidence/active/20260623-1026-PostgreSQL自定义指数持久化.md#L49-L51)**

### 性能优化建议

1. **连接池管理**：当前每次操作创建新连接，生产环境应使用连接池
2. **索引优化**：为常用查询字段添加索引
3. **批量操作**：对于大量数据操作使用批量插入

## 扩展与演进

### 未来改进方向

1. **连接池集成**：使用`psycopg_pool`或`SQLAlchemy`管理连接池
2. **全文搜索引擎**：集成PostgreSQL全文搜索或Elasticsearch
3. **数据版本控制**：支持指数定义的版本管理
4. **多租户支持**：添加用户/组织维度的数据隔离

### 相关文档

- [自定义指数管理](20-zi-ding-yi-zhi-shu-guan-li) - 智能体如何创建和管理自定义指数
- [RAG知识检索](19-ragzhi-shi-jian-suo) - 知识库在RAG系统中的作用
- [智能体架构](17-zhi-neng-ti-jia-gou) - 智能体系统的整体架构
- [系统架构](9-xi-tong-jia-gou) - 平台整体架构设计