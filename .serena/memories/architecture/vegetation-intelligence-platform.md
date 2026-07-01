# 植被指数智能分析平台

- 项目从零创建，分支 `feat/vegetation-intelligence-platform`。
- 后端位于 `backend/`：30种指数统一注册表在 `app/core/indices.py`；NumPy、Joblib、PyTorch CUDA引擎在 `app/engines/`；Rasterio分块流水线在 `app/services/raster_pipeline.py`。
- API入口为 `app/main.py` 与 `app/api/routes.py`，提供OGC风格process/job接口、智能体、资产检查、自定义公式、变化检测和地块统计。
- 智能体位于 `app/services/agent.py`，默认确定性规则，可选OpenAI兼容接口，必须确认后提交任务。
- 部署使用根目录 `compose.yml`，包括3个API、3个Worker、Redis、MinIO、Nacos、Traefik和Nacos桥；当前本机无Docker，未做运行态验证。
- 前端位于 `frontend/`，Vue 3 + TypeScript + Pinia + MapLibre + ECharts，主要组件在 `src/components/`。
- 已验证：Ruff通过、Pytest 14项通过、Vite生产构建通过、YAML解析通过、Playwright验证30指数加载与智能体方案生成。
- 当前环境未安装PyTorch/CUDA，Torch引擎已验证能回退Joblib，但真实GPU性能和显存行为仍需在NVIDIA机器验证。
- 任务证据见 `.evidence/active/20260622-1700-植被指数智能分析平台.md`。