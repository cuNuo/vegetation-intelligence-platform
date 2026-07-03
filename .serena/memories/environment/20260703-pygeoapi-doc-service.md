# pygeoapi 文档服务启动入口

- 本地开发默认后端为 `127.0.0.1:8011`，前端为 `127.0.0.1:5174`；不要把 Docker Traefik 的 `8080` 当成本地默认入口。
- 后端 `uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload` 启动时会自动准备 pygeoapi 运行配置和 OpenAPI 文档。
- pygeoapi 文档已挂载到同一个后端服务下：
  - 浏览器打开 `http://127.0.0.1:8011/processes` 会进入 pygeoapi Processes HTML 文档页。
  - 浏览器打开 `http://127.0.0.1:8011/openapi` 会进入 pygeoapi OpenAPI HTML 文档页。
  - 浏览器打开 `http://127.0.0.1:8011/pygeoapi` 会进入 pygeoapi 原生首页。
- 程序化调用 `/processes` 时保留现有平台 JSON 行为：`Accept: application/json` 或测试客户端调用仍返回 35 个指数的 OGC Processes 兼容目录。
- 运行期配置与 OpenAPI 生成到 `backend/data/pygeoapi/`，该目录通过 `backend/data/` 忽略，不应提交。
- 共享逻辑位于 `backend/app/services/pygeoapi_runtime.py`；独立备用脚本 `backend/scripts/start_pygeoapi.py` 复用同一逻辑，可用 `--port 5001` 启动单独 pygeoapi 服务。
- pygeoapi 0.21.0 的 CLI `pygeoapi serve` 在源码中固定 `debug=True`，Windows 下会派生 reloader 子进程；项目脚本改为导入 `pygeoapi.flask_app.APP` 并使用 `use_reloader=False` 启动，避免停止后残留端口占用。
- 当前通过 Starlette `WSGIMiddleware` 挂载 Flask APP；运行可用，但 Starlette 提示未来弃用。当前环境未安装 `a2wsgi`，后续升级可评估替换。