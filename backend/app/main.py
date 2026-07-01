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
    description="30种植被指数、多引擎分块计算、OGC兼容任务接口和智能推荐代理。",
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
    return {"status": "healthy", "service": settings.app_name}
