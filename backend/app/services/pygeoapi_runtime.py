# backend/app/services/pygeoapi_runtime.py
# 文件说明：pygeoapi 本地运行时配置与挂载辅助。
# 主要职责：生成 pygeoapi 配置/OpenAPI，设置环境变量，并加载 Flask 应用。
# 对外入口：prepare_pygeoapi_runtime、load_pygeoapi_flask_app、serve_pygeoapi_flask_app。
# 依赖边界：只编排 pygeoapi 运行环境，不承载指数计算业务逻辑。

"""pygeoapi文档服务运行时辅助。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
SOURCE_CONFIG = REPO_ROOT / "infra" / "pygeoapi" / "config.yml"
RUNTIME_DIR = BACKEND_ROOT / "data" / "pygeoapi"
RUNTIME_CONFIG = RUNTIME_DIR / "config.yml"
OPENAPI_FILE = RUNTIME_DIR / "openapi.yml"
DEFAULT_MOUNT_URL = "http://127.0.0.1:8011/pygeoapi"


def find_pygeoapi_executable() -> Path:
    """优先使用当前 Python 环境中的 pygeoapi CLI，避免误用全局环境。"""
    executable_name = "pygeoapi.exe" if os.name == "nt" else "pygeoapi"
    candidates = [
        Path(sys.prefix) / "Scripts" / executable_name,
        Path(sys.prefix) / "bin" / executable_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    located = shutil.which("pygeoapi")
    if located:
        return Path(located)
    raise FileNotFoundError(
        "未找到 pygeoapi CLI，请先在当前后端环境中安装项目依赖：python -m pip install -e \".[dev]\""
    )


def build_runtime_config(host: str, port: int, public_url: str) -> Path:
    """按目标访问地址生成运行期配置，避免直接改动 infra 模板。"""
    if not SOURCE_CONFIG.exists():
        raise FileNotFoundError(f"缺少 pygeoapi 配置模板：{SOURCE_CONFIG}")

    config_text = SOURCE_CONFIG.read_text(encoding="utf-8")
    config_text = config_text.replace("host: 0.0.0.0", f"host: {host}", 1)
    config_text = config_text.replace("port: 5000", f"port: {port}", 1)
    config_text = config_text.replace("url: http://localhost:5000", f"url: {public_url}", 1)

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIG.write_text(config_text, encoding="utf-8")
    return RUNTIME_CONFIG


def build_environment(config_path: Path, openapi_path: Path) -> dict[str, str]:
    """准备 pygeoapi 运行所需环境变量，并确保可导入 backend/app。"""
    env = os.environ.copy()
    env["PYGEOAPI_CONFIG"] = str(config_path)
    env["PYGEOAPI_OPENAPI"] = str(openapi_path)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(BACKEND_ROOT)
        if not existing_pythonpath
        else f"{BACKEND_ROOT}{os.pathsep}{existing_pythonpath}"
    )
    return env


def apply_pygeoapi_environment(env: dict[str, str]) -> None:
    """把 pygeoapi 环境写入当前进程，供导入期配置读取。"""
    os.environ.update(env)
    backend_path = str(BACKEND_ROOT)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def generate_openapi(pygeoapi: Path, config_path: Path, env: dict[str, str]) -> None:
    """生成 OpenAPI 文档，使 pygeoapi /openapi 返回最新接口描述。"""
    subprocess.run(
        [
            str(pygeoapi),
            "openapi",
            "generate",
            str(config_path),
            "--format",
            "yaml",
            "--output-file",
            str(OPENAPI_FILE),
        ],
        cwd=BACKEND_ROOT,
        env=env,
        check=True,
    )


def prepare_pygeoapi_runtime(
    *,
    public_url: str = DEFAULT_MOUNT_URL,
    host: str = "127.0.0.1",
    port: int = 8011,
) -> dict[str, str]:
    """生成配置和 OpenAPI，并返回可用于当前进程或子进程的环境变量。"""
    pygeoapi = find_pygeoapi_executable()
    config_path = build_runtime_config(host=host, port=port, public_url=public_url)
    env = build_environment(config_path, OPENAPI_FILE)
    generate_openapi(pygeoapi, config_path, env)
    return env


def load_pygeoapi_flask_app(public_url: str = DEFAULT_MOUNT_URL) -> Any:
    """加载 pygeoapi Flask APP，供 FastAPI 通过 WSGI 中间件挂载。"""
    env = prepare_pygeoapi_runtime(public_url=public_url)
    apply_pygeoapi_environment(env)

    from pygeoapi.flask_app import APP

    return APP


def serve_pygeoapi_flask_app(env: dict[str, str]) -> int:
    """启动 pygeoapi Flask 应用，并关闭 reloader，避免 Windows 下残留子进程占端口。"""
    apply_pygeoapi_environment(env)

    from pygeoapi.flask_app import APP, api_

    APP.run(
        debug=False,
        use_reloader=False,
        host=api_.config["server"]["bind"]["host"],
        port=api_.config["server"]["bind"]["port"],
    )
    return 0
