"""自动化任务接口：状态查询、手动触发、历史记录。"""
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import AutomationRun, User

router = APIRouter(prefix="/api/automation", tags=["automation"])
logger = logging.getLogger(__name__)

# 进程内锁：防止 run-now 并发触发
_run_lock = asyncio.Lock()


@router.get("/status")
def get_status(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """返回自动刷新配置和最近一次任务结果。"""
    from config import (
        AUTO_REFRESH_ENABLED, AUTO_REFRESH_TIME, AUTO_REFRESH_INTERVAL_HOURS,
        AUTO_REFRESH_TIMEZONE, AUTO_REFRESH_ON_STARTUP,
    )
    from automation_service import get_last_run
    last = get_last_run(session)
    return {
        "enabled": AUTO_REFRESH_ENABLED,
        "schedule_time": AUTO_REFRESH_TIME,
        "interval_hours": AUTO_REFRESH_INTERVAL_HOURS,
        "timezone": AUTO_REFRESH_TIMEZONE,
        "on_startup": AUTO_REFRESH_ON_STARTUP,
        "last_run": last.model_dump() if last else None,
    }


@router.post("/run-now")
async def run_now(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """手动触发一次刷新任务（仅刷新当前用户）。防止并发重复。"""
    if _run_lock.locked():
        raise HTTPException(409, "刷新任务正在执行，请稍后再试")

    async with _run_lock:
        from automation_service import run_single_user_job
        run = await asyncio.to_thread(run_single_user_job, session, user.id)
        return run.model_dump()


@router.get("/runs")
def list_runs(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[dict]:
    """返回最近 20 次自动化任务记录。"""
    runs = session.exec(
        select(AutomationRun)
        .order_by(AutomationRun.started_at.desc())
        .limit(20)
    ).all()
    return [r.model_dump() for r in runs]
