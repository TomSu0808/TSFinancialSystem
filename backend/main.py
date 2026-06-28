"""FastAPI 入口：初始化数据库、挂载路由、开 CORS。

本地启动：
    cd backend
    uvicorn main:app --reload
交互式文档： http://localhost:8000/docs
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS, check_production_config
from database import init_db
from routers import (
    auth, backup, fx, holdings, imports, notes, platforms, research, snapshots, summary, transactions,
)
from routers import ai_keys, automation, alerts
import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_production_config()
    init_db()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="个人资产管理平台 API", version="0.1.0", lifespan=lifespan)

# 跨域来源由配置控制（本地默认 *；上云时在 .env 收紧为正式域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(platforms.router)
app.include_router(holdings.router)
app.include_router(fx.router)
app.include_router(summary.router)
app.include_router(notes.router)
app.include_router(snapshots.router)
app.include_router(transactions.router)
app.include_router(imports.router)
app.include_router(backup.router)
app.include_router(research.router)
app.include_router(ai_keys.router)
app.include_router(automation.router)
app.include_router(alerts.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 托管前端：上云时把 `npm run build` 产物（frontend/dist）作为静态站点提供，
# 与 /api 同源，免去单独部署前端和跨域配置。本地用 `python dev.py start`
# 跑 Vite 开发服时不会进到这里（dist 不存在则整段跳过）。
# ---------------------------------------------------------------------------
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # /api/* 已由上面的路由处理；漏到这里的 /api 视为未命中接口
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        # 命中真实静态文件（favicon 等）就直接返回，否则回退到 index.html，
        # 交给前端 React Router 处理客户端路由。
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
