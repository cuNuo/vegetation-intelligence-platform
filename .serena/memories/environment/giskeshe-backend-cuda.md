# 后端固定运行环境 giskeshe

- 2026-06-22 按用户要求在本机 Miniconda 创建持久化环境 `giskeshe`，路径 `D:\miniconda\envs\giskeshe`，不再使用 Codex 临时 Python 作为后端默认环境。
- Python: 3.11.15。
- 后端安装命令：在 `backend/` 下执行 `D:\miniconda\Scripts\conda.exe run -n giskeshe python -m pip install -e ".[dev]"`。
- PyTorch CUDA 安装命令：`D:\miniconda\Scripts\conda.exe run -n giskeshe python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128`。
- 已安装并验证：`torch 2.11.0+cu128`，`torch.version.cuda == 12.8`，`torch.cuda.is_available() == True`，设备为 `NVIDIA GeForce RTX 4060 Laptop GPU`，GPU 张量计算正常。
- 后端能力检测：`app.services.planner.has_cuda()` 返回 True，`/api/system/capabilities` 逻辑返回 `cuda: True`。
- 真实后端 torch 引擎验证：用 4 波段临时 GeoTIFF 执行 `RasterPipeline().run(..., engine='torch')`，输出 `actualEngine=torch`、`fallbackReasons=[]`、结果文件存在，NDVI mean 约 0.454545。
- 验证结果：`ruff check .` 通过；`pytest -q` 结果为 21 passed，1 个 Starlette TestClient 上游弃用警告。
- 后端启动推荐直接用固定 Python：`cd D:\Users\24658\Desktop\软件工程\实习\backend; D:\miniconda\envs\giskeshe\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload`。