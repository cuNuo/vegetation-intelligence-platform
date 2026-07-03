# backend/scripts/start_pygeoapi.py
# 文件说明：本地启动独立 pygeoapi 文档与 OGC API 服务。
# 主要职责：生成运行期配置和 OpenAPI 文档，并调用 pygeoapi serve。
# 对外入口：命令行 main。
# 依赖边界：只编排 pygeoapi CLI，不重复实现 Processor 或计算逻辑。

"""启动本项目独立 pygeoapi 服务。"""

from __future__ import annotations

import argparse

from app.services.pygeoapi_runtime import (
    OPENAPI_FILE,
    RUNTIME_CONFIG,
    prepare_pygeoapi_runtime,
    serve_pygeoapi_flask_app,
)


def parse_args() -> argparse.Namespace:
    """解析本地启动参数。"""
    parser = argparse.ArgumentParser(description="启动植被指数平台的独立 pygeoapi 文档服务。")
    parser.add_argument("--host", default="127.0.0.1", help="pygeoapi 监听地址，默认 127.0.0.1。")
    parser.add_argument("--port", type=int, default=5000, help="pygeoapi 监听端口，默认 5000。")
    parser.add_argument(
        "--url",
        default=None,
        help="写入 OpenAPI 的对外访问地址，默认由 host/port 推导。",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="只生成运行期配置和 OpenAPI 文档，不启动服务。",
    )
    return parser.parse_args()


def main() -> int:
    """生成文档并启动 pygeoapi 原生服务。"""
    args = parse_args()
    public_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    service_url = args.url or f"http://{public_host}:{args.port}"
    env = prepare_pygeoapi_runtime(public_url=service_url, host=args.host, port=args.port)

    print(f"pygeoapi 配置：{RUNTIME_CONFIG}")
    print(f"pygeoapi OpenAPI：{OPENAPI_FILE}")
    print(f"pygeoapi 首页：{service_url}")
    print(f"pygeoapi OpenAPI 文档：{service_url}/openapi")
    print(f"pygeoapi Processes：{service_url}/processes")

    if args.generate_only:
        return 0

    try:
        return serve_pygeoapi_flask_app(env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
