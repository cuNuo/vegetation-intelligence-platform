# 2026-07-02 公式展示、35 指数与全服务验证

- 旧服务文档 `docx/已开发服务(3).docx` 列出 NDVI、BNDVI、GNDVI、NormB、GLI、GR、MSR、TVI、RVI、RDVI；平台原有 30 个任务书指数已覆盖 NDVI/GNDVI/GLI/TVI/RVI，本次补齐缺失的 `bndvi`、`normb`、`gr`、`msr`、`rdvi`。
- 后端注册表现在是 35 个内置指数：30 个任务书指数 + 5 个旧服务兼容指数。同步修改批量请求上限、能力接口、任务书覆盖文案、OpenAPI 描述和测试断言。
- 前端 `IndexCatalog.vue` 的公式展示改为结构化 token 公式卡片，按波段、函数、参数、数字、运算符分层显示；搜索范围包含公式文本；状态栏和指数库默认计数为 35。
- `RasterPipeline` 在窗口读取时会把 Rasterio mask 和源 nodata 转为 `NaN`，避免 `bajiepart1.tif` 的极小 float nodata 进入公式造成 overflow warning。
- `backend/app/settings.py` 读取顺序包含仓库根 `.env`，从 `backend/` 启动服务时也能拿到 PostgreSQL、MinIO、LLM、天地图等环境配置。
- `bajiepart1.tif` 是 6 波段 float32 测试影像，默认映射应使用 Blue=1、Green=2、Red=3、NIR=4、SWIR1=5、SWIR2=6、RedEdge=0；前端 store 已按此设置。需要红边的指数必须另行映射红边波段。
- 全流程验证通过：inspect、upload、同步 batch、异步 batch、jobs/results、indices、agent plan、天地图首页与右侧智能体均正常。LLM 状态为 `used`，provider 为 `openai-compatible`；PostgreSQL 存储状态正常；能力接口返回 `cuda=true`、`indexCount=35`、`totalIndexCount=35`。
- 验证命令：后端 `ruff check .` 通过；后端 `pytest -q` 为 29 passed，1 个 Starlette TestClient 上游弃用警告；前端 `npm run build` 通过，仅 Vite 大 chunk 警告。
- 证据日志：`.evidence/active/20260702-0115-公式展示35指数与全服务验证.md`。截图：`output/playwright/formula-catalog-35-20260702.png`、`output/playwright/fullservice-home-20260702.png`。
