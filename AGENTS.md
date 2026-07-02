# AGENTS.md

## 1. 使用原则与规则继承

- 本仓库首先继承全局规范 `D:\.codex\AGENTS.md`，本文件只补充植被指数智能分析平台的项目事实、目录边界、任务书要求和开发入口。
- 全局规范中的中文沟通、Sequential Thinking、`update_plan`、安全命令、Hook 优先、原子化 patch、evidence 与 Serena memory 收口等要求继续有效，不在本文件重复展开。
- 默认知识加载顺序为：项目根 `AGENTS.md` -> `.serena/memories/` -> `.evidence/` -> `docs/`。
- 进入任务后先判断工作流类型，再按需加载最少的专题资料；禁止为了“了解项目”无目的地全文扫描所有源码和历史日志。
- 任何说明、注释和手册都必须以当前代码为准。任务书或旧文档与实现冲突时，应明确区分“已实现”“部分实现”“规划项”，不得把规划当成现状。

## 2. 项目定位

本仓库实现“植被指数提取算法封装与 Web 服务实现”实习任务，目标是把遥感植被指数算法封装为可复用、可扩展、可通过 OGC 风格接口调用的智能分析平台。

平台包含以下核心能力：

1. 统一植被指数注册表，当前内置 35 个指数，其中包含任务书要求的至少 30 个指数和 5 个旧服务兼容指数。
2. NumPy、Joblib、PyTorch 三种计算引擎，共用同一套公式定义。
3. Rasterio 分块窗口读取、计算和写出，避免大幅影像一次性载入内存。
4. FastAPI 提供 REST 与 OGC API - Processes 风格接口。
5. Celery + Redis 提供部署模式异步任务队列，本地开发模式可使用线程池或 eager 模式。
6. MinIO 管理输入影像和结果工件，PostgreSQL 可持久化自定义指数、Agent 知识和会话事件。
7. pygeoapi 通过动态 `SpectralIndexProcessor` 暴露标准 Process。
8. Nacos 注册服务实例，Nacos Bridge 生成 Traefik File Provider 动态路由。
9. Vue 3 遥感工作台负责影像上传、波段映射、指数浏览、任务进度、地图叠加、统计图表和智能体交互。
10. 植被分析 Agent 负责理解需求、检索知识、推荐指数、生成执行单和解释结果；未经用户确认不得提交计算任务。

## 3. 任务书硬约束

重大修改前必须对照 `docx/植被指数提取算法封装与Web服务实现实习任务书.docx`。以下能力不得被删除或绕过：

- 至少 30 种任务书植被指数。
- 所有公式集中在统一注册表，不得在 API、Worker、前端或不同引擎中重复维护公式。
- Rasterio 分块或窗口处理，不允许大影像默认整幅读入内存。
- 同步和异步 OGC API - Processes 调用。
- Celery + Redis 任务队列。
- MinIO 工件存储。
- Nacos 服务发现和 Traefik 网关路由。
- Vue 3 可视化工作台。
- Agent 先推荐、后确认、再提交的安全边界。

如确需偏离任务书，必须在实现、测试、evidence 和交付说明中同时记录原因、影响与替代方案。

## 4. 仓库目录与职责

```text
.
|-- AGENTS.md                         项目规则与知识入口
|-- README.md                         运行、接口和使用说明
|-- compose.yml                       完整容器编排
|-- backend/
|   |-- app/
|   |   |-- api/                      HTTP 请求模型和路由
|   |   |-- core/                     纯算法注册表
|   |   |-- engines/                  NumPy/Joblib/PyTorch 计算引擎
|   |   |-- services/                 栅格、任务、资产、Agent、存储和分析服务
|   |   |-- main.py                   FastAPI 应用入口
|   |   |-- worker_tasks.py           Celery Worker 入口
|   |   |-- pygeoapi_processor.py     pygeoapi 动态处理器
|   |   |-- nacos_bridge.py           Nacos 到 Traefik 的路由同步
|   |   `-- settings.py               环境配置
|   |-- tests/                        后端单元与接口测试
|   `-- scripts/benchmark.py          多引擎基准脚本
|-- frontend/
|   |-- src/
|   |   |-- components/               地图、Agent、资产、任务和统计组件
|   |   |-- composables/              API 与主题组合式函数
|   |   |-- stores/                   Pinia 工作台状态
|   |   |-- types/                    前后端契约类型
|   |   |-- App.vue                   应用主编排
|   |   `-- main.ts                   Vue 启动入口
|   `-- vite.config.js                Vite 开发与代理配置
|-- infra/
|   |-- pygeoapi/config.yml           pygeoapi Process 注册
|   `-- traefik/traefik.yml           网关配置
|-- docx/                             任务书、报告模板和汇报主手册
|-- .serena/memories/                 长期稳定项目知识
`-- .evidence/                        任务、运行、截图和数据工件证据
```

## 5. 后端分层边界

### 5.1 公式核心层

- `backend/app/core/indices.py` 是所有内置公式和元数据的唯一事实源。
- `IndexDefinition` 同时描述指数编号、中文名、公式、所需逻辑波段、参数、分类、用途、限制和可执行表达式。
- 公式表达式只能依赖传入的数组后端 `xp`、逻辑波段数组和参数，不得导入 Rasterio、FastAPI、Celery、MinIO 或数据库模块。
- 新增指数必须同步补充固定数组测试、公开元数据、波段要求、预期范围、推荐标签和限制。
- 所有除法优先使用 `safe_divide`，避免分母接近零时产生 `inf` 或 `NaN` 扩散。

### 5.2 计算引擎层

- `NumpyEngine` 是兼容性基线。
- `JoblibEngine` 并行计算同一窗口内的多个指数；公式结果必须与 NumPy 保持一致。
- `TorchEngine` 在 CUDA 可用时执行 GPU 计算，失败或不可用时必须记录原因并回退。
- 引擎只负责数组计算和结果清洗，不负责文件路径、HTTP、任务状态或对象存储。
- 新引擎必须实现 `ComputeEngine` 协议并通过跨引擎一致性测试。

### 5.3 栅格流水线层

- `RasterPipeline` 负责源影像解析、波段验证、窗口生成、共享读取、引擎调用、顺序写出、统计、预览、上传和 manifest。
- 分块大小限制为 128 至 2048；写出 GeoTIFF 的块大小需满足 TIFF 分块要求。
- 多指数计算必须共享同一窗口的波段读取，禁止为每个指数重复读取相同窗口。
- Rasterio mask 和源 nodata 必须转换为无效值语义，再由引擎统一写成输出 nodata。
- 输出必须保留源影像 CRS、仿射变换、宽高和像元网格。
- 进度以已完成窗口数为基础，不得使用无法解释的虚假百分比。

### 5.4 服务与任务层

- `backend/app/api/routes.py` 只做协议转换、输入校验、异常到 HTTP 状态码映射和服务编排。
- `JobManager` 统一管理本地线程池与 Celery 两种异步路径。
- `worker_tasks.py` 只能包装同一个 `RasterPipeline`，不得另写一套计算流程。
- 同步请求直接返回结果；带 `Prefer: respond-async` 的请求返回任务记录和结果地址。
- 取消、失败、回退和结果读取必须保持可观察。

### 5.5 资产与存储层

- `assets.py` 负责本地路径、上传文件、MinIO 对象、影像元数据、内部 overview 和预览。
- 文件名前缀传感器配置只能补全缺失元数据，不能覆盖 GeoTIFF 已有的波段描述和波长。
- 任何外部路径都必须经过允许目录检查或对象键解析，禁止任意路径读取。
- 密钥、MinIO 凭据、天地图令牌和 LLM Token 只能通过环境变量提供。

### 5.6 Agent 层

- Agent 的推荐依据必须优先来自指数注册表和知识检索结果。
- LLM 只负责自然语言理解与候选意图增强，不直接执行 Python、访问任意路径或提交任务。
- 执行单必须经过后端二次校验：指数可执行、波段齐全、波段号有效、路径存在。
- 计划确认接口是计算提交的唯一 Agent 路径。
- 外部知识、用户输入和模型输出均视为不可信数据，必须通过结构化模型或白名单校验。

## 6. 前端分层边界

- Vue 统一使用 Vue 3 Composition API、`<script setup lang="ts">` 和 TypeScript。
- `usePlatformApi.ts` 是 HTTP/SSE 调用入口；组件不得重复手写同类请求解析。
- `workspace.ts` 是资产、波段映射、任务、结果和活动面板的单一状态源。
- `App.vue` 只负责编排全局刷新、组件通信和视图切换。
- `MapWorkspace.vue` 负责 MapLibre 图层、底图、影像范围、瓦片叠加、定位和对比模式。
- `AssetToolbar.vue` 负责上传、资产选择、波段映射和批量提交。
- `IndexCatalog.vue` 负责指数检索、分类和公式展示。
- `AgentDrawer.vue` 负责会话、SSE 思考过程、执行单编辑、确认和结果解读。
- `JobProgressPanel.vue` 负责任务状态、进度、吞吐估算、结果切换和取消。
- `StatisticsDashboard.vue` 负责统计信息和 ECharts 图表生命周期。
- UI 改动必须检查桌面与窄屏布局，不允许控件重叠、文字溢出或地图区域不可操作。

## 7. API 与接口文档约定

- FastAPI 主接口文档：后端启动后访问 `/docs`。
- FastAPI ReDoc：后端启动后访问 `/redoc`。
- OpenAPI JSON：后端启动后访问 `/openapi.json`。
- 健康检查：`GET /health`。
- 指数目录：`GET /api/indices`。
- OGC Process 目录：`GET /processes`。
- OGC Process 描述：`GET /processes/{process_id}`。
- Process 执行：`POST /processes/{process_id}/execution`。
- 异步任务：`GET /jobs`、`GET /jobs/{job_id}`、`GET /jobs/{job_id}/results`、`DELETE /jobs/{job_id}`。
- pygeoapi 独立服务由 `infra/pygeoapi/config.yml` 注册 `spectral-index` Process，处理器为 `app.pygeoapi_processor.SpectralIndexProcessor`。
- 修改请求或响应字段时，必须同步 Pydantic Schema、前端 TypeScript 类型、API 调用封装、测试和主手册。

## 8. 固定开发环境与命令

后端固定使用 Miniconda 环境：

```powershell
cd backend
D:\miniconda\envs\giskeshe\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload
```

前端开发：

```powershell
cd frontend
npm run dev
```

后端质量检查：

```powershell
cd backend
D:\miniconda\envs\giskeshe\python.exe -m ruff check .
D:\miniconda\envs\giskeshe\python.exe -m pytest -q
```

前端生产构建：

```powershell
cd frontend
npm run build
```

完整容器环境：

```powershell
docker compose up --build
```

## 9. 测试要求

- 测试文件命名为 `test_*.py`。
- 指数层必须覆盖注册表数量、关键公式固定数组、有限值和跨引擎一致性。
- 栅格层必须覆盖窗口计算、空间参考、输出尺寸、nodata 和统计。
- API 层必须覆盖健康检查、Process 目录、同步/异步任务、上传、瓦片、Agent 安全边界和错误输入。
- Agent 必须覆盖缺失波段阻断、未确认不执行、知识隔离、自定义指数和结果解释。
- UI 改动至少执行 `npm run build`；涉及地图、上传、SSE 或响应式布局时增加真实浏览器验证。
- CUDA、Docker、MinIO、Nacos 等当前机器无法验证的能力必须在交付说明中明确标记，不得写成已通过。

## 10. 注释与文档要求

- 新增或修改的源码必须保留中文文件头，说明文件职责、关键入口、依赖边界和维护约束。
- 公开类、函数、接口处理器和复杂内部函数应使用中文 docstring 或 JSDoc，解释“为什么这样设计、输入输出、异常和边界”。
- 行内注释只用于算法推导、状态机、并发、缓存、空间坐标、回退和安全校验等不直观逻辑，不逐行翻译代码。
- 源码清单、目录设计、模块划分、接口设计、pygeoapi、指数注册表和分块流水线的正式导读统一见：
  - `docx/植被指数智能分析平台源代码与实现主手册.docx`
- 任务书是需求依据，主手册是代码导读，README 是运行入口，三者职责不得混淆。

## 11. Security 与配置

- 禁止提交真实密钥、Token、数据库密码和大体积 GeoTIFF。
- 环境变量以 `.env.example` 为模板；若模板缺失或被删除，交付时必须明确提示。
- 影像路径、对象键、自定义公式、GeoJSON 和 LLM 输出均需校验。
- 自定义公式仅允许白名单 AST 节点、函数和波段名。
- 日志和 evidence 中出现敏感字段时必须打码。

## 12. Evidence、Memory 与维护

- 每次任务开始和结束维护 `.evidence/active/` 日志，并更新 `.evidence/manifest.csv`。
- 稳定架构、环境、长期坑位和使用入口写入 `.serena/memories/`；单次执行过程留在 `.evidence/`。
- 已存在大量 Serena topic，优先按 `architecture/`、`environment/`、`frontend/` 等主题读取，不新建含义重复的 memory。
- 修改项目入口、正式文档或运行方式后，检查 README、相关 memory 和 evidence 是否仍一致。
- 默认不自动执行 `git commit`。需要提交时使用 Conventional Commits，并在 PR 中写明任务书条目、验证结果、截图和环境假设。

## 13. 交付前检查

1. 代码、注释和主手册是否描述同一套真实实现。
2. 是否保持注册表为公式唯一事实源。
3. 是否保持大影像分块处理和多指数共享读取。
4. 是否保持 Agent 未确认不提交任务。
5. Ruff、pytest、前端 build 是否通过。
6. DOCX 是否完成渲染和全页视觉检查。
7. 无法验证的 CUDA、Docker、MinIO、Nacos 能力是否如实说明。
8. `.evidence/manifest.csv` 和 Serena memory 是否完成收口。
