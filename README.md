# 植被指数智能分析平台

面向遥感植被分析的实习项目，提供 30 种指数、Rasterio 分块计算、NumPy / Joblib / PyTorch CUDA 多引擎、OGC API - Processes 兼容接口、异步任务、智能方案推荐和 Vue 地图工作台。

## 核心能力

- 一份公式注册表同时驱动 NumPy、Joblib 和 PyTorch。
- GeoTIFF 按窗口读写，不将整幅大型影像载入内存或显存。
- 自动选择计算引擎；CUDA 不可用或显存不足时回退 CPU。
- 支持同步执行、Celery 异步执行、五级优先队列、进度查询和取消。
- 规则优先、LLM 可插拔的分析代理，用户确认后才提交任务。
- MapLibre 结果叠加、任务面板、指数目录和 ECharts 统计图。
- 日间/夜间双主题、可折叠工具面板、固定状态栏和流式响应式工作台。
- Docker Compose 编排三 API、三 Worker、Redis、MinIO、Nacos 和 Traefik。

## 本地开发

后端固定使用本机 Miniconda 环境 `giskeshe`，路径为 `D:\miniconda\envs\giskeshe`。该环境已安装项目依赖、开发依赖和 PyTorch CUDA：

- Python 3.11.15
- PyTorch 2.11.0+cu128
- CUDA 可用，已验证 RTX 4060 Laptop GPU

首次换机或重建环境时执行：

```powershell
cd D:\Users\24658\Desktop\软件工程\实习\backend
D:\miniconda\Scripts\conda.exe create -n giskeshe python=3.11 -y
D:\miniconda\Scripts\conda.exe run -n giskeshe python -m pip install -e ".[dev]"
D:\miniconda\Scripts\conda.exe run -n giskeshe python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

启动后端：

```powershell
cd D:\Users\24658\Desktop\软件工程\实习\backend
D:\miniconda\envs\giskeshe\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload
```

另开终端启动前端：

```powershell
cd D:\Users\24658\Desktop\软件工程\实习\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

浏览器访问 `http://127.0.0.1:5174`。前端支持按钮选择 GeoTIFF、拖拽导入、批量队列和批量处理，不再要求用户手动输入后端绝对路径。默认波段映射为 Blue=1、Green=2、Red=3、RedEdge=4、NIR=5、SWIR1=6、SWIR2=7，可在前端状态或接口请求中调整。

前端顶部工具栏可切换日间/夜间主题、隐藏智能体/任务/指数面板并跳转工作区；主题偏好保存在浏览器本地。底部状态栏持续显示 API、CUDA/CPU、队列和当前结果状态。地图和统计图会随窗口及面板尺寸自动重绘。

## 容器部署

安装 Docker Desktop、Docker Compose 和 NVIDIA Container Toolkit 后：

```powershell
docker compose -f compose.yml up --build
```

- 平台入口：`http://localhost:8080`
- Traefik 面板：`http://localhost:8081`
- MinIO 控制台：`http://localhost:9001`
- Nacos：`http://localhost:8848/nacos`

若没有 NVIDIA GPU，可注释 `worker-gpu` 服务；系统仍可通过 NumPy 和 Joblib 工作。

## 主要接口

- `GET /api/indices`
- `GET /processes`
- `POST /processes/{indexId}/execution`
- `POST /processes/batch/execution`
- `GET /jobs/{jobId}`
- `GET /jobs/{jobId}/results`
- `POST /api/assets/inspect`
- `POST /api/agent/plan`
- `POST /api/agent/plans/{planId}/confirm`
- `POST /api/formulas/validate`
- `POST /api/analysis/change`
- `POST /api/analysis/zonal-statistics`
- `GET /api/system/capabilities`

异步执行时添加请求头：

```text
Prefer: respond-async
```

## 测试与基准

```powershell
cd backend
pytest
ruff check .
python scripts/benchmark.py --size 2048 --repeats 3

cd ..\frontend
npm run build
```

基准结果需要在目标硬件运行；GPU 对小影像不一定更快，自动规划器会避免不必要的数据传输。

## 智能体安全边界

智能体只负责意图分类、波段检查、指数推荐和结构化方案生成。它不生成任意 Python 代码、不接收任意输出路径，也不会在用户确认前提交计算。

## 当前边界

- 不包含身份认证、多租户、计费和生产级高可用。
- 时序变化检测的数据配准与辐射归一化需要上游保证。
- pygeoapi 插件和配置位于 `backend/app/pygeoapi_processor.py` 与 `infra/pygeoapi/config.yml`。
- Traefik 不原生支持 Nacos，本项目通过 `app.nacos_bridge` 原子生成 File Provider 配置。
