本文档系统性地解析植被指数智能分析平台后端的模块划分、职责边界与目录组织原则。后端采用**分层架构**设计，以 `backend/app/` 为核心，通过清晰的依赖方向和接口契约，将API协议、业务逻辑、计算引擎和基础设施解耦为可独立演进的模块。

## 整体架构概览

后端遵循**四层分层架构**：API协议层、业务服务层、计算引擎层和核心定义层。依赖方向严格向下，禁止反向依赖，确保核心逻辑的零框架耦合。

```mermaid
graph TB
    subgraph "API 协议层"
        A[api/routes.py] --> B[api/schemas.py]
    end
    
    subgraph "业务服务层"
        C[services/agent.py] --> D[services/raster_pipeline.py]
        E[services/assets.py] --> F[services/tiles.py]
        G[services/jobs.py] --> H[services/planner.py]
        I[services/agent_tools.py] --> J[services/agent_session_store.py]
        K[services/agent_knowledge_store.py] --> L[services/custom_index_store.py]
        M[services/advanced_analysis.py] --> N[services/nacos.py]
    end
    
    subgraph "计算引擎层"
        O[engines/base.py] --> P[engines/numpy_engine.py]
        O --> Q[engines/joblib_engine.py]
        O --> R[engines/torch_engine.py]
    end
    
    subgraph "核心定义层"
        S[core/indices.py]
    end
    
    subgraph "基础设施"
        T[main.py] --> U[settings.py]
        V[celery_app.py] --> W[worker_tasks.py]
        X[nacos_bridge.py] --> Y[pygeoapi_processor.py]
    end
    
    A --> C
    A --> D
    A --> E
    A --> G
    A --> I
    A --> K
    A --> M
    D --> O
    D --> H
    I --> K
    I --> L
    C --> I
    C --> J
    D --> E
    
    style A fill:#e1f5fe
    style S fill:#f3e5f5
    style O fill:#e8f5e8
    style D fill:#fff3e0
```

**架构分层说明**：
- **API协议层**：处理HTTP请求/响应转换、输入验证和错误映射
- **业务服务层**：实现领域逻辑，协调核心计算与外部资源
- **计算引擎层**：提供多后端计算抽象，支持CPU/GPU异构执行
- **核心定义层**：维护公式注册表，零框架依赖的纯逻辑定义

## 目录结构详解

后端采用**功能模块化**的目录组织，每个模块具有明确的职责边界和稳定的公共接口。

### 顶层目录结构

```
backend/
├── Dockerfile          # 基础镜像定义
├── Dockerfile.gpu      # GPU支持镜像
├── app/                # 主应用代码
│   ├── __init__.py     # 包标识
│   ├── api/            # API协议层
│   ├── core/           # 核心定义层
│   ├── engines/        # 计算引擎层
│   ├── services/       # 业务服务层
│   ├── main.py         # FastAPI入口
│   ├── settings.py     # 配置管理
│   ├── celery_app.py   # Celery配置
│   ├── worker_tasks.py # Celery任务
│   ├── nacos_bridge.py # Nacos桥接
│   └── pygeoapi_processor.py # OGC处理器
├── pyproject.toml      # 项目配置与依赖
├── scripts/            # 工具脚本
└── tests/              # 测试套件
```

### 模块职责矩阵

| 模块路径 | 核心职责 | 对外接口 | 依赖边界 |
|---------|---------|---------|---------|
| `api/routes.py` | HTTP协议转换、路由分发、异常映射 | `router` (APIRouter) | 不实现业务逻辑 |
| `api/schemas.py` | 请求/响应数据模型、字段验证 | Pydantic模型 | 只做契约校验 |
| `core/indices.py` | 植被指数统一注册表、公式定义 | `INDEX_REGISTRY`, `IndexDefinition` | 零框架依赖 |
| `engines/base.py` | 计算引擎公共协议、结果清洗 | `ComputeEngine`, `EngineResult` | 不负责I/O |
| `engines/numpy_engine.py` | NumPy基线引擎、顺序计算 | `NumpyEngine` | 跨引擎正确性基线 |
| `engines/joblib_engine.py` | Joblib CPU并行计算 | `JoblibEngine` | 不并行写入 |
| `engines/torch_engine.py` | PyTorch CUDA计算、GPU回退 | `TorchEngine` | 不构建梯度 |
| `services/raster_pipeline.py` | Rasterio分块计算、统计、预览 | `RasterPipeline`, `RasterTask` | 所有执行路径共用 |
| `services/jobs.py` | 任务状态管理、进度跟踪 | `JobManager`, `JobRecord` | 统一调用RasterPipeline |
| `services/agent.py` | 植被分析智能体、意图识别 | `VegetationAgent` | LLM只增强理解 |
| `services/agent_tools.py` | 指数知识检索、动态注册 | `search_index_knowledge`, `register_custom_index` | 动态表达式白名单验证 |
| `services/assets.py` | GeoTIFF资产管理、元数据解析 | `inspect_raster`, `save_uploaded_asset` | 路径安全解析 |
| `services/tiles.py` | GeoTIFF动态瓦片渲染 | `render_geotiff_tile` | 路径限制在数据目录 |
| `services/planner.py` | 计算引擎自动选择 | `ExecutionPlanner` | 只做可解释决策 |
| `services/advanced_analysis.py` | 自定义公式、变化检测、地块统计 | `validate_custom_expression`, `detect_change` | 禁止任意代码执行 |
| `services/agent_session_store.py` | 会话事件存储 | `create_session`, `append_event` | 只保存会话事实 |
| `services/agent_knowledge_store.py` | 外部知识库存储与召回 | `save_knowledge_document`, `search_persisted_knowledge` | 查询文本不作为指令执行 |
| `services/custom_index_store.py` | 自定义指数PostgreSQL持久化 | `save_custom_index`, `load_custom_indices` | 故障状态交由上层决定 |
| `services/nacos.py` | Nacos服务注册与心跳 | `NacosRegistration` | 注册失败不阻断开发 |
| `celery_app.py` | Celery应用与优先队列配置 | `celery_app` | 计算统一复用RasterPipeline |
| `worker_tasks.py` | Celery Worker栅格任务入口 | `process_raster` | 不得复制公式 |
| `main.py` | FastAPI应用装配入口 | `app`, `lifespan`, `health` | 业务逻辑下沉到services |
| `settings.py` | 应用配置模型 | `Settings`, `settings` | 只定义配置 |
| `nacos_bridge.py` | Nacos到Traefik动态路由同步 | `fetch_instances`, `render_configuration` | 只同步服务发现信息 |
| `pygeoapi_processor.py` | pygeoapi动态植被指数处理器 | `SpectralIndexProcessor` | 复用注册表与RasterPipeline |

## 核心模块深度解析

### 1. 核心定义层 (`core/`)

核心定义层是后端的**零依赖基础**，维护植被指数的统一注册表和公式定义。所有计算引擎共享同一套公式定义，确保逻辑一致性。

**IndexDefinition 数据类**：
```python
@dataclass(frozen=True, slots=True)
class IndexDefinition:
    id: str                      # 指数唯一标识
    name: str                    # 中文名称
    formula: str                 # 数学公式描述
    required_bands: tuple[str, ...]  # 所需逻辑波段
    expression: Expression       # 跨数组后端表达式
    description: str             # 用途说明
    expected_range: tuple[float, float] | None  # 期望值域
    parameters: dict[str, float] # 可配置参数
    categories: tuple[str, ...]  # 分类标签
    recommendation_tags: tuple[str, ...]  # 推荐场景
    limitations: tuple[str, ...] # 使用限制
    amp_safe: bool              # 混合精度安全标志
```

**设计原则**：
- **表达式注入**：公式函数接收 `xp` 参数（NumPy或PyTorch），实现跨后端复用
- **安全除法**：统一通过 `safe_divide` 避免无穷值污染
- **元数据驱动**：每个指数携带完整的业务元数据，支持智能推荐和结果解释

**注册表结构**：
```python
INDEX_REGISTRY: dict[str, IndexDefinition] = {
    item.id: item for item in INDEX_DEFINITIONS
}
```

目前注册了**35种植被指数**，涵盖植被覆盖、叶绿素、水分胁迫、变化监测等类别。

### 2. 计算引擎层 (`engines/`)

计算引擎层提供**多后端抽象**，支持NumPy基线、Joblib CPU并行和PyTorch GPU加速。引擎选择由 `ExecutionPlanner` 根据数据规模和硬件能力自动决策。

**引擎协议**：
```python
class ComputeEngine(Protocol):
    name: str
    
    def compute(
        self,
        definitions: list[IndexDefinition],
        bands: dict[str, np.ndarray],
        parameters: dict[str, dict[str, float]] | None = None,
    ) -> EngineResult:
        """计算一个窗口内的多个指数，并返回统一结果结构。"""
        ...
```

**引擎特性对比**：

| 引擎 | 并行策略 | 适用场景 | 回退机制 |
|------|---------|---------|---------|
| NumpyEngine | 顺序执行 | 小型任务、同步执行、正确性基线 | 无（基线） |
| JoblibEngine | 线程并行 | 中大型任务、CPU环境 | 导入失败回退NumPy |
| TorchEngine | GPU并行 | 大型任务、多指数、CUDA可用 | CUDA不可用回退Joblib |

**回退链**：TorchEngine → JoblibEngine → NumpyEngine，确保任何环境下都能执行计算。

### 3. 业务服务层 (`services/`)

业务服务层是后端的**逻辑核心**，协调核心计算、外部资源和领域规则。每个服务具有单一职责和明确的依赖边界。

#### 3.1 栅格处理管道 (`raster_pipeline.py`)

**核心职责**：协调窗口读取、共享计算、顺序写出、统计和产物登记。

**关键设计**：
- **波段共享**：同一窗口中每个物理波段只读取一次，多个指数共享 `arrays`，避免"指数数量 × 磁盘读取次数"的I/O放大
- **进度回调**：通过 `ProgressCallback` 支持任务进度实时上报
- **取消支持**：通过 `CancelCallback` 支持任务中途取消

**处理流程**：
```mermaid
sequenceDiagram
    participant Client as 客户端
    participant Pipeline as RasterPipeline
    participant Engine as 计算引擎
    participant Assets as 资产服务
    
    Client->>Pipeline: RasterTask
    Pipeline->>Pipeline: 验证波段映射
    Pipeline->>Pipeline: 选择计算引擎
    Pipeline->>Pipeline: 生成窗口迭代器
    
    loop 每个窗口
        Pipeline->>Pipeline: 读取物理波段
        Pipeline->>Engine: 计算指数
        Engine-->>Pipeline: EngineResult
        Pipeline->>Pipeline: 写出结果波段
        Pipeline->>Pipeline: 更新进度
    end
    
    Pipeline->>Pipeline: 计算统计信息
    Pipeline->>Pipeline: 生成预览图
    Pipeline->>Assets: 登记产物
    Pipeline-->>Client: 任务结果
```

#### 3.2 任务管理器 (`jobs.py`)

**核心职责**：维护任务从排队到终态的状态、进度、耗时、取消、结果和失败信息。

**双模式执行**：
- **开发模式** (`celery_always_eager=True`)：使用线程池本地执行
- **部署模式** (`celery_always_eager=False`)：提交到Celery分布式队列

**任务状态机**：
```mermaid
stateDiagram-v2
    [*] --> accepted: 提交任务
    accepted --> running: 开始执行
    running --> successful: 执行成功
    running --> failed: 执行失败
    running --> dismissed: 任务取消
    running --> running: 进度更新
    
    note right of accepted: 等待执行
    note right of running: 正在计算
    note right of successful: 结果就绪
    note right of failed: 错误信息
    note right of dismissed: 已取消
```

#### 3.3 植被分析智能体 (`agent.py`)

**核心职责**：将自然语言目标转换为可解释、可编辑且需确认的分析方案。

**设计哲学**：
- **人机协同**：LLM只增强理解，未确认不得执行
- **规则优先**：基于关键词匹配的规则引擎覆盖常见场景
- **知识增强**：结合RAG和网络搜索提供专业建议

**意图识别规则**：

| 意图 | 关键词 | 推荐指数 | 场景描述 |
|------|-------|---------|---------|
| growth | 长势、健康、覆盖、生物量 | NDVI, EVI, GNDVI | 作物长势空间差异分析 |
| sparse | 稀疏、苗期、裸土、荒漠 | SAVI, OSAVI, MSAVI, BSI | 稀疏植被与裸土背景分析 |
| chlorophyll | 叶绿素、氮、营养、红边 | GNDVI, NDRE, GCI, RECI | 叶绿素与氮素状态分析 |
| water_stress | 干旱、水分、缺水、胁迫 | NDVI, NDMI, MSI | 植被水分胁迫辅助分析 |
| change | 变化、两期、前后、退化 | NDVI, EVI, NBR | 多时相植被变化监测 |

#### 3.4 资产服务 (`assets.py`)

**核心职责**：GeoTIFF资产检查、元数据解析、传感器波段识别和MinIO适配。

**传感器自动识别**：

| 传感器模式 | 波段数 | 传感器类型 | 典型波段 |
|-----------|-------|-----------|---------|
| `GF01*` | 4 | GF-1 | Blue, Green, Red, NIR |
| `LAD08*` | 7 | Landsat 8/9 OLI | Coastal, Blue, Green, Red, NIR, SWIR1, SWIR2 |
| `LAD09*` | 7 | Landsat 8/9 OLI | 同LAD08 |
| `SHB02*` | 4 | Sentinel-2A/2B MSI | Blue, Green, Red, NIR |

**金字塔构建**：自动为大型影像生成2倍金字塔层级，直到最长边接近256像素。

#### 3.5 瓦片服务 (`tiles.py`)

**核心职责**：GeoTIFF/COG动态地图瓦片渲染，按Web Mercator范围读取、拉伸并输出PNG。

**关键特性**：
- **路径安全**：限制在数据目录内，防止路径遍历攻击
- **缓存策略**：LRU缓存最近访问的瓦片，文件更新后自动失效
- **坐标转换**：支持Web Mercator (EPSG:3857) 到源坐标系的动态重投影

#### 3.6 高级分析服务 (`advanced_analysis.py`)

**核心职责**：安全自定义公式、分块变化检测和GeoJSON地块统计。

**安全验证**：
- **AST白名单**：遍历语法树，拒绝白名单之外的名称、调用和语法
- **函数限制**：只允许 `abs`, `sqrt`, `minimum`, `maximum`
- **运算符限制**：只允许算术运算符，禁止比较、逻辑和属性访问

#### 3.7 持久化服务

**会话存储** (`agent_session_store.py`)：
- **双存储策略**：PostgreSQL持久化 + 内存回退
- **事件模型**：结构化事件追加，支持会话回放

**知识存储** (`agent_knowledge_store.py`)：
- **文档导入**：支持用户上传外部知识文档
- **词项评分**：基于关键词匹配的知识召回

**自定义指数存储** (`custom_index_store.py`)：
- **Upsert语义**：支持指数定义的创建和更新
- **JSON字段**：存储复杂结构的元数据

### 4. API协议层 (`api/`)

#### 4.1 路由设计 (`routes.py`)

**路由分组**：

| 路由前缀 | 功能组 | 主要端点 |
|---------|-------|---------|
| `/api/indices` | 指数管理 | 列出指数、指数详情 |
| `/processes` | OGC Processes | 列出过程、过程描述、执行过程 |
| `/jobs` | 任务管理 | 任务列表、任务状态、任务取消 |
| `/api/agent` | 智能体 | 创建计划、确认计划、结果解释 |
| `/api/recipes` | 分析方案 | 方案列表、创建方案 |
| `/api/formulas` | 公式管理 | 公式验证 |
| `/tiles` | 瓦片服务 | GeoTIFF瓦片渲染 |
| `/api/indices/custom` | 自定义指数 | 注册自定义指数 |
| `/api/agent/knowledge` | 知识管理 | 导入知识文档 |

**OGC兼容设计**：
- **Processes端点**：完全符合OGC API - Processes规范
- **同步/异步执行**：通过 `Prefer` 头选择执行模式
- **任务状态查询**：标准的任务状态和进度接口

#### 4.2 数据模型 (`schemas.py`)

**核心模型**：

| 模型 | 用途 | 关键字段 |
|------|-----|---------|
| `ExecutionRequest` | 任务执行请求 | source, indices, bands, engine, blockSize, priority |
| `AgentPlanRequest` | 智能体计划请求 | message, sessionId, availableBands, llmConfig |
| `ConfirmPlanRequest` | 确认计划请求 | source, bands, engine, blockSize, priority |
| `CustomFormulaRequest` | 自定义公式请求 | expression, allowedBands |
| `AgentCustomIndexRequest` | 自定义指数请求 | id, name, expression, description, categories |

**验证规则**：
- **字段别名**：支持camelCase和snake_case
- **范围约束**：如blockSize在128-2048之间
- **跨字段验证**：如objectKey与localPath至少提供一个

### 5. 基础设施模块

#### 5.1 FastAPI入口 (`main.py`)

**装配职责**：
- **生命周期管理**：启动时创建数据目录、加载持久化指数、注册Nacos
- **中间件配置**：CORS、Prometheus监控
- **路由注册**：包含所有API路由
- **静态文件**：挂载artifacts目录

#### 5.2 配置管理 (`settings.py`)

**配置项**：

| 配置项 | 环境变量 | 默认值 | 说明 |
|-------|---------|-------|------|
| `app_name` | `VIP_APP_NAME` | 植被指数智能分析平台 | 应用名称 |
| `data_dir` | `VIP_DATA_DIR` | data | 数据目录 |
| `redis_url` | `VIP_REDIS_URL` | redis://localhost:6379/0 | Redis连接 |
| `celery_always_eager` | `VIP_CELERY_ALWAYS_EAGER` | True | 本地执行模式 |
| `database_url` | `VIP_DATABASE_URL` | None | PostgreSQL连接 |
| `minio_*` | `VIP_MINIO_*` | ... | MinIO配置 |
| `openai_*` | `VIP_OPENAI_*` | ... | OpenAI配置 |
| `nacos_url` | `VIP_NACOS_URL` | None | Nacos地址 |

#### 5.3 Celery配置 (`celery_app.py`)

**五级优先队列**：
- `urgent` (priority.1)：紧急任务
- `high` (priority.2)：高优先级
- `normal` (priority.3)：普通任务（默认）
- `low` (priority.4)：低优先级
- `batch` (priority.5)：批量任务

#### 5.4 服务发现 (`nacos_bridge.py`)

**Nacos到Traefik同步**：
- **健康实例查询**：只查询健康且启用的实例
- **原子配置生成**：生成Traefik File Provider配置
- **服务映射**：vegetation-basic → /api/basic, vegetation-adjusted → /api/adjusted, vegetation-advanced → /api/advanced

## 模块交互模式

### 1. 计算任务执行流程

```mermaid
sequenceDiagram
    participant Client as 前端
    participant API as api/routes.py
    participant JobMgr as services/jobs.py
    participant Pipeline as services/raster_pipeline.py
    participant Planner as services/planner.py
    participant Engine as engines/*
    participant Assets as services/assets.py
    
    Client->>API: POST /processes/{id}/execution
    API->>API: 验证请求参数
    API->>JobMgr: submit(task, priority)
    
    alt 本地模式
        JobMgr->>JobMgr: 线程池提交
        JobMgr->>Pipeline: run(task)
    else 分布式模式
        JobMgr->>JobMgr: Celery提交
        Note over JobMgr: worker_tasks.py
        JobMgr->>Pipeline: run(task)
    end
    
    Pipeline->>Planner: choose(width, height, ...)
    Planner-->>Pipeline: ExecutionDecision
    Pipeline->>Pipeline: 验证波段映射
    
    loop 每个窗口
        Pipeline->>Pipeline: 读取波段数据
        Pipeline->>Engine: compute(definitions, bands)
        Engine-->>Pipeline: EngineResult
        Pipeline->>Pipeline: 写出结果
        Pipeline->>JobMgr: 进度回调
    end
    
    Pipeline->>Pipeline: 计算统计
    Pipeline->>Pipeline: 生成预览
    Pipeline->>Assets: upload_artifact()
    Pipeline-->>JobMgr: 任务结果
    JobMgr-->>API: 任务状态
    API-->>Client: 响应
```

### 2. 智能体交互流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant API as api/routes.py
    participant Agent as services/agent.py
    participant Tools as services/agent_tools.py
    participant Session as services/agent_session_store.py
    participant Knowledge as services/agent_knowledge_store.py
    
    User->>API: POST /api/agent/plans
    API->>Agent: create_plan(message, ...)
    Agent->>Session: create_session(message)
    Agent->>Agent: 意图识别（规则匹配）
    Agent->>Tools: search_index_knowledge(keywords)
    Tools->>Knowledge: search_persisted_knowledge(keywords)
    Knowledge-->>Tools: 知识文档
    Tools-->>Agent: 指数知识
    Agent->>Agent: 生成分析方案
    Agent->>Session: append_event(plan)
    Agent-->>API: 计划方案
    API-->>User: 可编辑的方案
    
    User->>API: POST /api/agent/plans/{id}/confirm
    API->>Agent: mark_confirmed(plan_id, ...)
    Agent->>Agent: 验证执行单
    API->>JobMgr: submit(task)
    JobMgr-->>API: 任务ID
    API-->>User: 确认结果
```

### 3. 瓦片渲染流程

```mermaid
sequenceDiagram
    participant Map as 地图前端
    participant API as api/routes.py
    participant Tiles as services/tiles.py
    participant Rasterio as Rasterio
    participant Cache as LRU缓存
    
    Map->>API: GET /tiles/{key}/{z}/{x}/{y}.png
    API->>Tiles: render_geotiff_tile(key, z, x, y)
    Tiles->>Tiles: resolve_tile_key(key)
    Tiles->>Tiles: 获取文件stat
    
    alt 缓存命中
        Tiles->>Cache: 查询缓存
        Cache-->>Tiles: 缓存瓦片
    else 缓存未命中
        Tiles->>Rasterio: 打开GeoTIFF
        Rasterio-->>Tiles: 数据集
        Tiles->>Tiles: 计算瓦片边界
        Tiles->>Tiles: 重投影到EPSG:3857
        Tiles->>Tiles: 拉伸渲染
        Tiles->>Tiles: 生成PNG
        Tiles->>Cache: 存入缓存
    end
    
    Tiles-->>API: PNG字节
    API-->>Map: 瓦片图像
```

## 设计模式与架构原则

### 1. 分层依赖原则

**依赖方向**：API → Services → Core/Engines，禁止反向依赖。

**接口隔离**：
- API层只依赖服务层的公共接口
- 服务层通过依赖注入使用基础设施
- 核心层零框架依赖，可独立测试

### 2. 策略模式应用

**计算引擎选择**：
```python
class ExecutionPlanner:
    def choose(self, width, height, band_count, index_count, requested, is_synchronous):
        # 根据规模和硬件选择引擎
        if requested != "auto":  # 用户指定
            return requested
        if is_synchronous or pixels < 2_000_000:  # 小型任务
            return "numpy"
        if has_cuda() and (pixels >= 20_000_000 or index_count >= 4):  # 大型任务
            return "torch"
        return "joblib"  # 中型任务
```

### 3. 仓库模式

**统一注册表**：
```python
INDEX_REGISTRY: dict[str, IndexDefinition] = {
    item.id: item for item in INDEX_DEFINITIONS
}

def get_index(index_id: str) -> IndexDefinition:
    """获取指数定义，不存在则抛出ValueError"""
    try:
        return INDEX_REGISTRY[index_id]
    except KeyError:
        raise ValueError(f"未知植被指数: {index_id}")
```

### 4. 双存储策略

**PostgreSQL + 内存回退**：
```python
def create_session(title: str) -> str:
    session_id = str(uuid.uuid4())
    _MEMORY_SESSIONS[session_id] = {...}  # 总是写入内存
    if not initialize_agent_session_store():  # 尝试数据库
        return session_id  # 数据库不可用，使用内存
    # 写入数据库
    ...
```

### 5. 安全边界设计

**AST白名单验证**：
```python
class SafeExpressionValidator(ast.NodeVisitor):
    def visit_Name(self, node):
        if node.id not in self.allowed_names and node.id not in ALLOWED_FUNCTIONS:
            raise ValueError(f"表达式包含未允许名称: {node.id}")
    
    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
            raise ValueError("只允许abs、sqrt、minimum、maximum函数")
```

## 配置与部署

### 环境变量配置

```bash
# 应用配置
VIP_APP_NAME=植被指数智能分析平台
VIP_DATA_DIR=/data

# 数据库配置
VIP_REDIS_URL=redis://redis:6379/0
VIP_DATABASE_URL=postgresql://user:pass@postgres:5432/vegetation
VIP_CELERY_ALWAYS_EAGER=false

# MinIO配置
VIP_MINIO_ENDPOINT=minio:9000
VIP_MINIO_ACCESS_KEY=vegetation
VIP_MINIO_SECRET_KEY=vegetation-secret
VIP_MINIO_ENABLED=true

# LLM配置
VIP_OPENAI_BASE_URL=https://api.openai.com/v1
VIP_OPENAI_API_KEY=sk-...
VIP_OPENAI_MODEL=gpt-4.1-mini

# 服务发现
VIP_NACOS_URL=http://nacos:8848
VIP_SERVICE_NAME=vegetation-basic
VIP_SERVICE_HOST=api-basic
VIP_SERVICE_PORT=8000
```

### Docker多阶段构建

**基础镜像** (`Dockerfile`)：
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**GPU镜像** (`Dockerfile.gpu`)：
```dockerfile
FROM nvidia/cuda:12.1-runtime
# 安装PyTorch和依赖
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
# 其余同基础镜像
```

## 测试策略

### 测试目录结构

```
tests/
├── conftest.py              # 测试配置和fixtures
├── test_api.py              # API端点测试
├── test_agent.py            # 智能体逻辑测试
├── test_indices.py          # 指数计算测试
├── test_raster_pipeline.py  # 栅格管道测试
├── test_advanced_analysis.py # 高级分析测试
└── test_assets.py           # 资产服务测试
```

### 测试覆盖重点

1. **指数计算正确性**：验证所有35个指数的数学公式
2. **引擎一致性**：确保NumPy、Joblib、Torch引擎结果一致
3. **API契约**：验证请求/响应符合OpenAPI规范
4. **安全边界**：测试AST白名单、路径遍历防护
5. **错误处理**：验证异常情况下的优雅降级

## 扩展指南

### 添加新指数

1. 在 `core/indices.py` 的 `INDEX_DEFINITIONS` 中添加定义
2. 指定 `id`, `name`, `formula`, `required_bands`, `expression`
3. 添加 `categories`, `recommendation_tags`, `limitations` 元数据
4. 运行测试验证：`pytest tests/test_indices.py`

### 添加新引擎

1. 在 `engines/` 目录创建新引擎类
2. 实现 `ComputeEngine` 协议的 `compute` 方法
3. 在 `services/planner.py` 的 `ExecutionPlanner.choose` 中添加选择逻辑
4. 在 `api/schemas.py` 的 `ExecutionRequest.engine` 枚举中添加新引擎

### 添加新API端点

1. 在 `api/schemas.py` 中定义请求/响应模型
2. 在 `api/routes.py` 中添加路由函数
3. 实现业务逻辑（通常委托给services层）
4. 添加测试用例

## 相关文档导航

- **平台架构**：[平台整体架构与技术栈](4-ping-tai-zheng-ti-jia-gou-yu-ji-zhu-zhan) - 了解整体技术选型
- **计算引擎**：[多引擎选择与自动回退策略](8-duo-yin-qing-xuan-ze-yu-zi-dong-hui-tui-ce-lue) - 深入引擎选择逻辑
- **智能体设计**：[植被分析 Agent 设计哲学与安全边界](10-zhi-bei-fen-xi-agent-she-ji-zhe-xue-yu-an-quan-bian-jie) - 理解智能体架构
- **API规范**：[REST 接口与 OGC API - Processes 规范对齐](16-rest-jie-kou-yu-ogc-api-processes-gui-fan-dui-qi) - 了解API设计
- **测试策略**：[后端测试策略与 pytest 覆盖范围](26-hou-duan-ce-shi-ce-lue-yu-pytest-fu-gai-fan-wei) - 掌握测试方法
- **部署配置**：[Docker Compose 服务编排全景](23-docker-compose-fu-wu-bian-pai-quan-jing) - 了解容器化部署