本页面详细介绍植被指数智能分析平台后端的完整环境搭建流程，涵盖 Python 运行环境、依赖管理、外部服务配置及开发工具链。无论您是首次搭建开发环境还是需要迁移至新机器，均可按本文指引逐步完成后端环境配置。

## 技术栈概览

后端采用 Python 3.11 + FastAPI 构建 REST API，通过 Celery 实现异步任务调度，支持 NumPy / Joblib / PyTorch 三种计算引擎。核心依赖通过 `pyproject.toml` 统一管理，使用 Miniconda 隔离开发环境，确保依赖一致性。

| 组件 | 技术选型 | 版本要求 | 作用 |
|------|----------|----------|------|
| **运行时** | Python | ≥3.11, <3.14 | 应用执行环境 |
| **Web 框架** | FastAPI + Uvicorn | ≥0.115 / ≥0.34 | HTTP API 服务 |
| **任务队列** | Celery + Redis | ≥5.4 / 7.x | 异步任务调度 |
| **配置管理** | pydantic-settings | ≥2.7 | 环境变量验证 |
| **栅格处理** | Rasterio + NumPy | ≥1.4 / ≥2.0 | GeoTIFF 读写与计算 |
| **GPU 加速** | PyTorch | ≥2.6 (可选) | CUDA 并行计算 |
| **对象存储** | MinIO | ≥7.2 (可选) | 资产文件存储 |
| **服务发现** | Nacos | v2.4.3 (可选) | 多实例注册与负载均衡 |
| **持久化** | PostgreSQL | 14+ (可选) | 自定义指数持久化 |

Sources: [pyproject.toml](backend/pyproject.toml#L6-L29)

## 环境搭建流程

```mermaid
flowchart TD
    A[开始环境搭建] --> B{Miniconda 已安装?}
    B -->|否| C[安装 Miniconda]
    B -->|是| D[创建 giskeshe 环境]
    C --> D
    D --> E[安装项目依赖]
    E --> F{需要 GPU 加速?}
    F -->|是| G[安装 PyTorch CUDA]
    F -->|否| H[跳过 GPU 依赖]
    G --> I[配置环境变量]
    H --> I
    I --> J{需要外部服务?}
    J -->|是| K[配置 Redis/PostgreSQL/MinIO]
    J -->|否| L[使用默认配置]
    K --> M[启动后端服务]
    L --> M
    M --> N[验证环境]
    N --> O[环境搭建完成]
```

## Python 运行环境

### Miniconda 环境配置

平台使用 Miniconda 管理 Python 环境，指定环境名称为 `giskeshe`，路径为 `D:\miniconda\envs\giskeshe`。此设计确保所有开发者使用一致的 Python 版本和依赖树，避免"在我机器上能跑"的问题。

```powershell
# 1. 创建 conda 环境（首次运行）
D:\miniconda\Scripts\conda.exe create -n giskeshe python=3.11 -y

# 2. 安装项目依赖（开发模式，包含 pytest、ruff 等开发工具）
cd D:\Users\24658\Desktop\软件工程\实习\backend
D:\miniconda\Scripts\conda.exe run -n giskeshe python -m pip install -e ".[dev]"

# 3. （可选）安装 PyTorch CUDA 支持
D:\miniconda\Scripts\conda.exe run -n giskeshe python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**参数说明**：
- `-e`: 以"可编辑"模式安装，修改代码后无需重新安装
- `".[dev]"`: 安装项目本身及 `[dev]` 可选依赖组（pytest、ruff）
- `cu128`: CUDA 12.8 版本的 PyTorch 预编译包

Sources: [README.md](README.md#L24-L31), [pyproject.toml](backend/pyproject.toml#L31-L37)

### 依赖清单

核心依赖与可选依赖的版本范围如下表所示：

| 依赖包 | 版本范围 | 分组 | 用途 |
|--------|----------|------|------|
| celery[redis] | ≥5.4, <6 | core | 异步任务队列与 Redis Broker |
| fastapi | ≥0.115, <1 | core | Web API 框架 |
| uvicorn[standard] | ≥0.34, <1 | core | ASGI 服务器 |
| rasterio | ≥1.4, <2 | core | GeoTIFF 栅格读写 |
| numpy | ≥2.0, <3 | core | 数值计算引擎 |
| joblib | ≥1.4, <2 | core | 多进程并行引擎 |
| langchain | ≥0.3, <1 | core | 智能体框架 |
| langchain-openai | ≥0.3, <1 | core | OpenAI 兼容 LLM 集成 |
| langchain-anthropic | ≥0.3, <1 | core | Anthropic Claude 集成 |
| minio | ≥7.2, <8 | core | MinIO 对象存储客户端 |
| psycopg[binary] | ≥3.2, <4 | core | PostgreSQL 数据库驱动 |
| pygeoapi | ≥0.20, <1 | core | OGC API 兼容层 |
| pydantic | ≥2.10, <3 | core | 数据验证与序列化 |
| pydantic-settings | ≥2.7, <3 | core | 环境变量配置管理 |
| httpx | ≥0.28, <1 | core | 异步 HTTP 客户端 |
| prometheus-client | ≥0.21, <1 | core | 指标暴露 |
| torch | ≥2.6 | gpu | PyTorch GPU 计算引擎 |
| pytest | ≥8.3, <9 | dev | 测试框架 |
| pytest-asyncio | ≥0.25, <1 | dev | 异步测试支持 |
| ruff | ≥0.9, <1 | dev | 代码风格检查 |

Sources: [pyproject.toml](backend/pyproject.toml#L10-L29), [vegetation_intelligence_platform.egg-info/requires.txt](backend/vegetation_intelligence_platform.egg-info/requires.txt#L1-L23)

## 环境变量配置

### 配置模型

应用通过 `pydantic-settings` 管理所有可配置参数。所有环境变量以 `VIP_` 为前缀，支持通过 `.env` 文件或系统环境变量注入。

```mermaid
flowchart LR
    subgraph 配置来源
        A[".env 文件"]
        B["系统环境变量"]
        C["代码默认值"]
    end
    
    subgraph Settings 类
        D["pydantic-settings 解析"]
        D --> E["类型验证"]
        D --> F["默认值填充"]
    end
    
    subgraph 应用配置
        G["settings 单例"]
    end
    
    A --> D
    B --> D
    C --> D
    E --> G
    F --> G
```

### 完整环境变量清单

| 变量名 | 类型 | 默认值 | 必需 | 说明 |
|--------|------|--------|------|------|
| `VIP_REDIS_URL` | string | `redis://localhost:6379/0` | 否 | Redis 连接地址，Celery Broker |
| `VIP_CELERY_ALWAYS_EAGER` | bool | `true` | 否 | `true` 时任务同步执行（开发模式） |
| `VIP_DATABASE_URL` | string | `None` | 否 | PostgreSQL 连接串，启用自定义指数持久化 |
| `VIP_MINIO_ENDPOINT` | string | `localhost:9000` | 否 | MinIO 服务地址 |
| `VIP_MINIO_ACCESS_KEY` | string | `vegetation` | 否 | MinIO 访问密钥 |
| `VIP_MINIO_SECRET_KEY` | string | `vegetation-secret` | 否 | MinIO 秘密密钥 |
| `VIP_MINIO_SECURE` | bool | `false` | 否 | 是否启用 HTTPS |
| `VIP_MINIO_BUCKET` | string | `vegetation-assets` | 否 | MinIO 存储桶名称 |
| `VIP_MINIO_ENABLED` | bool | `false` | 否 | 是否启用 MinIO 对象存储 |
| `VIP_OPENAI_BASE_URL` | string | `None` | 否 | OpenAI 兼容 API 地址 |
| `VIP_OPENAI_API_KEY` | string | `None` | 否 | OpenAI API 密钥 |
| `VIP_OPENAI_MODEL` | string | `gpt-4.1-mini` | 否 | 使用的 LLM 模型名称 |
| `VIP_SERVICE_NAME` | string | `vegetation-basic` | 否 | Nacos 注册服务名 |
| `VIP_SERVICE_HOST` | string | `api-basic` | 否 | Nacos 注册主机名 |
| `VIP_SERVICE_PORT` | int | `8000` | 否 | Nacos 注册端口 |
| `VIP_NACOS_URL` | string | `None` | 否 | Nacos 服务发现地址 |
| `VIP_DATA_DIR` | Path | `data` | 否 | 数据文件根目录 |

Sources: [settings.py](backend/app/settings.py#L8-L33), [.env.example](.env.example#L1-L16)

### 配置 `.env` 文件

在项目根目录下创建 `.env` 文件。最小化本地开发只需配置 Celery 行为：

```bash
# === 最小化配置（本地开发） ===
VIP_CELERY_ALWAYS_EAGER=true

# === 可选：PostgreSQL 持久化自定义指数 ===
# VIP_DATABASE_URL=postgresql://postgres:change-me@127.0.0.1:5432/vegetation_intelligence

# === 可选：OpenAI 兼容模型（智能体意图分类） ===
# VIP_OPENAI_BASE_URL=https://api.openai.com/v1
# VIP_OPENAI_API_KEY=sk-...
# VIP_OPENAI_MODEL=gpt-4.1-mini

# === 可选：MinIO 对象存储 ===
# VIP_MINIO_ENABLED=true
# VIP_MINIO_ENDPOINT=localhost:9000
# VIP_MINIO_ACCESS_KEY=vegetation
# VIP_MINIO_SECRET_KEY=vegetation-secret
```

**关键提示**：`VIP_CELERY_ALWAYS_EAGER=true` 使 Celery 任务在主线程同步执行，省去启动 Redis 和 Worker 的步骤，适用于功能开发和调试。容器化部署时，此值必须设为 `false`。

Sources: [.env.example](.env.example#L1-L16), [settings.py](backend/app/settings.py#L28)

## 外部服务依赖

### 服务依赖矩阵

并非所有外部服务都是必需的。下表列出各服务与平台功能的对应关系：

| 服务 | 本地开发 | 容器部署 | 功能影响 |
|------|----------|----------|----------|
| **Redis** | 可选 | 必需 | Celery 异步任务队列的 Broker 和 Backend |
| **PostgreSQL** | 可选 | 可选 | 自定义植被指数的持久化存储 |
| **MinIO** | 可选 | 可选 | 上传文件与计算结果的对象存储 |
| **Nacos** | 可选 | 可选 | 多 API 实例的服务注册与发现 |

当 `VIP_CELERY_ALWAYS_EAGER=true` 时，Redis 非必需，任务在 FastAPI 主线程同步执行。当 `VIP_MINIO_ENABLED=false`（默认）时，文件存储使用本地 `data/` 目录。

Sources: [settings.py](backend/app/settings.py#L11-L19), [celery_app.py](backend/app/celery_app.py#L28)

### Redis（任务队列）

Redis 作为 Celery 的消息中间件和结果后端。本地开发可选择安装 Redis for Windows 或通过 Docker 运行：

```powershell
# 方式一：Docker 快速启动 Redis
docker run -d --name redis -p 6379:6379 redis:7.4-alpine redis-server --appendonly yes

# 方式二：容器化部署时由 compose.yml 自动编排
```

连接配置通过 `VIP_REDIS_URL` 设置，格式为 `redis://<host>:<port>/<db>`。

Sources: [compose.yml](compose.yml#L144-L154), [celery_app.py](backend/app/celery_app.py#L8-L13)

### PostgreSQL（可选）

PostgreSQL 用于持久化用户自定义的植被指数公式。本地开发可通过以下方式启动：

```powershell
# Docker 启动 PostgreSQL
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=change-me -e POSTGRES_DB=vegetation_intelligence postgres:16-alpine
```

在 `.env` 中配置连接串后，应用启动时自动创建所需的表结构。

Sources: [.env.example](.env.example#L9-L10), [settings.py](backend/app/settings.py#L13)

### MinIO（可选）

MinIO 提供 S3 兼容的对象存储，用于存放上传的 GeoTIFF 文件和计算结果：

```powershell
# Docker 启动 MinIO
docker run -d --name minio -p 9000:9000 -p 9001:9001 -e MINIO_ROOT_USER=vegetation -e MINIO_ROOT_PASSWORD=vegetation-secret minio/minio server /data --console-address ":9001"
```

MinIO 控制台地址：`http://localhost:9001`，默认用户名 `vegetation`，密码 `vegetation-secret`。

Sources: [compose.yml](compose.yml#L156-L172), [settings.py](backend/app/settings.py#L14-L19)

## 启动后端服务

### 本地开发启动

```powershell
cd D:\Users\24658\Desktop\软件工程\实习\backend
D:\miniconda\envs\giskeshe\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload
```

| 参数 | 说明 |
|------|------|
| `--host 127.0.0.1` | 仅监听本地回环地址 |
| `--port 8011` | 后端 API 端口（前端 Vite 代理目标） |
| `--reload` | 代码变更后自动重启，开发模式推荐启用 |

启动成功后，终端输出：
```
INFO:     Uvicorn running on http://127.0.0.1:8011 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

应用启动时会自动执行以下初始化：
1. 创建 `data/inputs` 和 `data/outputs` 目录（如不存在）
2. 从 PostgreSQL 加载已持久化的自定义指数（若已配置）
3. 尝试向 Nacos 注册服务实例（若已配置）

Sources: [main.py](backend/app/main.py#L17-L28), [README.md](README.md#L46-L50)

### 验证服务运行

```powershell
# 健康检查
curl http://127.0.0.1:8011/health

# 查看内置指数目录
curl http://127.0.0.1:8011/api/indices

# 查看 OGC Processes 列表
curl http://127.0.0.1:8011/processes
```

健康检查应返回 `{"status": "healthy", "service": "植被指数智能分析平台"}`。

Sources: [main.py](backend/app/main.py#L52-L54), [routes.py](backend/app/api/routes.py#L1-L40)

## 后端目录结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口与生命周期管理
│   ├── settings.py             # pydantic-settings 配置模型
│   ├── celery_app.py           # Celery 实例与五级优先队列
│   ├── nacos_bridge.py         # Nacos → Traefik File Provider 桥接
│   ├── pygeoapi_processor.py   # pygeoapi OGC 兼容插件
│   ├── worker_tasks.py         # Celery 任务定义
│   ├── api/
│   │   ├── routes.py           # REST 路由定义
│   │   └── schemas.py          # Pydantic 请求/响应模型
│   ├── core/
│   │   └── indices.py          # 植被指数注册表（30 种内置公式）
│   ├── engines/
│   │   ├── base.py             # 引擎抽象基类
│   │   ├── numpy_engine.py     # NumPy CPU 计算引擎
│   │   ├── joblib_engine.py    # Joblib 多进程引擎
│   │   └── torch_engine.py     # PyTorch CUDA 引擎
│   └── services/
│       ├── agent.py            # 智能体核心逻辑
│       ├── agent_tools.py      # 智能体工具集
│       ├── agent_knowledge_store.py  # RAG 知识库存储
│       ├── agent_session_store.py    # 会话历史存储
│       ├── advanced_analysis.py # 变化检测与统计分析
│       ├── assets.py           # 资产管理（上传/检查）
│       ├── custom_index_store.py     # 自定义指数存储
│       ├── jobs.py             # 任务管理
│       ├── nacos.py            # Nacos 注册客户端
│       ├── planner.py          # 自动引擎规划器
│       └── raster_pipeline.py  # 栅格分块处理流水线
├── tests/                      # 测试套件
├── scripts/
│   └── benchmark.py            # 多引擎性能基准
├── pyproject.toml              # 项目元数据与依赖
├── Dockerfile                  # CPU 版容器镜像
└── Dockerfile.gpu              # GPU Worker 容器镜像
```

Sources: [目录结构](backend/)

## 测试环境

### 运行测试

```powershell
cd D:\Users\24658\Desktop\软件工程\实习\backend

# 运行全部测试
pytest

# 运行特定测试文件
pytest tests/test_api.py
pytest tests/test_indices.py

# 运行基准测试
python scripts/benchmark.py --size 2048 --repeats 3

# 代码风格检查
ruff check .
```

测试配置通过 `pyproject.toml` 中的 `[tool.pytest.ini_options]` 定义，将项目根目录加入 `pythonpath`，测试目录为 `tests/`。`conftest.py` 提供 `sample_raster` fixture，生成包含 Blue/Green/Red/NIR 四波段的测试 GeoTIFF 文件。

Sources: [pyproject.toml](backend/pyproject.toml#L39-L42), [conftest.py](backend/tests/conftest.py#L1-L29)

### 测试覆盖范围

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_api.py` | REST API 端点、OGC 接口、智能体安全边界 |
| `test_indices.py` | 植被指数公式正确性 |
| `test_raster_pipeline.py` | 栅格分块读写、多引擎计算 |
| `test_agent.py` | 智能体意图识别、方案生成 |
| `test_advanced_analysis.py` | 变化检测、分区统计 |

Sources: [tests/](backend/tests/)

## 容器化环境

### 镜像说明

后端提供两个 Dockerfile：

| 镜像 | 基础镜像 | 用途 | 入口命令 |
|------|----------|------|----------|
| `Dockerfile` | `python:3.12-slim` | API 服务和 CPU Worker | `uvicorn app.main:app` |
| `Dockerfile.gpu` | `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime` | GPU Worker | `celery worker -Q urgent,high,normal` |

两个镜像都安装了 `libgdal-dev` 系统依赖以支持 Rasterio 的 GDAL 绑定。

Sources: [Dockerfile](backend/Dockerfile#L1-L18), [Dockerfile.gpu](backend/Dockerfile.gpu#L1-L17)

### 服务拓扑

容器化部署包含 9 个服务，通过 Traefik 统一入口：

```mermaid
flowchart TB
    Client[浏览器] --> Traefik[Traefik :8080]
    
    subgraph API服务层
        Basic[api-basic<br/>基础 API]
        Adjusted[api-adjusted<br/>调整 API]
        Advanced[api-advanced<br/>高级 API]
    end
    
    subgraph Worker层
        WN[worker-numpy<br/>CPU 串行]
        WJ[worker-joblib<br/>CPU 并行]
        WG[worker-gpu<br/>CUDA]
    end
    
    subgraph 基础设施
        Redis[(Redis 7.4)]
        MinIO[(MinIO)]
        Nacos[(Nacos)]
        Frontend[Frontend<br/>Vue + Nginx]
    end
    
    Traefik --> Frontend
    Traefik --> Basic
    Traefik --> Adjusted
    Traefik --> Advanced
    
    Basic --> Redis
    Adjusted --> Redis
    Advanced --> Redis
    
    Redis --> WN
    Redis --> WJ
    Redis --> WG
    
    Basic --> MinIO
    NacosBridge[nacos-bridge] --> Nacos
    NacosBridge --> Traefik
```

Sources: [compose.yml](compose.yml#L1-L192)

## 常见问题排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| `ModuleNotFoundError: No module named 'app'` | 未以可编辑模式安装 | 在 backend 目录执行 `pip install -e .` |
| `rasterio` 安装失败 | 缺少 GDAL 系统库 | Windows: 使用 conda 安装; Linux: `apt install libgdal-dev` |
| `torch` 安装后 CUDA 不可用 | PyTorch 版本与 CUDA 不匹配 | 确认使用 `--index-url https://download.pytorch.org/whl/cu128` |
| Celery 任务卡住不执行 | `CELERY_ALWAYS_EAGER=false` 但 Redis 未启动 | 设为 `true` 或启动 Redis |
| `VIP_DATABASE_URL` 连接失败 | PostgreSQL 未启动或密码错误 | 检查 Docker 容器状态和连接串 |
| 8011 端口被占用 | 其他进程占用端口 | 更换端口或终止占用进程 |
| `pydantic.ValidationError` 启动失败 | `.env` 文件中变量格式错误 | 检查变量名是否带 `VIP_` 前缀 |

## 下一步

环境配置完成后，建议按以下顺序继续探索：

1. **[前端环境配置](4-qian-duan-huan-jing-pei-zhi)** — 配置 Vue 前端开发环境并连接后端 API
2. **[容器化部署](5-rong-qi-hua-bu-shu)** — 使用 Docker Compose 一键部署完整微服务架构
3. **[后端架构](10-hou-duan-jia-gou)** — 深入了解 FastAPI 应用结构与服务分层设计
4. **[计算引擎](14-ji-suan-yin-qing)** — 理解 NumPy / Joblib / PyTorch 多引擎抽象与自动选择机制
5. **[任务调度系统](16-ren-wu-diao-du-xi-tong)** — 了解 Celery 五级优先队列与任务生命周期管理