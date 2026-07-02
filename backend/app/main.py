# backend/app/main.py
# 文件说明：FastAPI 应用装配入口。
# 主要职责：注册生命周期、CORS、静态目录、路由、监控和健康检查。
# 对外入口：app、lifespan、health。
# 依赖边界：业务逻辑下沉到 services。

"""FastAPI应用入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.api.routes import router
from app.services.agent_tools import load_persisted_custom_indices
from app.services.nacos import nacos_registration
from app.settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """管理应用启动加载与 Nacos 注册生命周期。"""
    (settings.data_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "outputs").mkdir(parents=True, exist_ok=True)
    load_persisted_custom_indices()
    try:
        await nacos_registration.start()
    except Exception:
        pass
    yield
    await nacos_registration.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="35种植被指数、多引擎分块计算、OGC兼容任务接口和智能推荐代理。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
app.mount(
    "/artifacts",
    StaticFiles(directory=Path(settings.data_dir), check_dir=False),
    name="artifacts",
)


@app.get("/health")
def health() -> dict[str, str]:
    """返回不依赖外部服务的进程健康状态。"""
    return {"status": "healthy", "service": settings.app_name}
