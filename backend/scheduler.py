"""轻量 asyncio 调度器：每日定时触发全量刷新任务。

不引入 Celery / APScheduler / Redis 等外部依赖。
FastAPI lifespan 里调用 start() / stop()。

防重启重复逻辑：
- 进程内用模块级 _task 保证只有一个 asyncio Task。
- uvicorn --reload 每次 reload 都是新进程，不会累积。
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None


def _seconds_to_next(time_str: str, interval_hours: int, tz_name: str) -> float:
    """计算距离下次触发还有多少秒。"""
    import zoneinfo
    tz = zoneinfo.ZoneInfo(tz_name)
    now = datetime.now(tz=tz)
    h, m = map(int, time_str.split(":"))
    target_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if now >= target_today:
        target = target_today + timedelta(hours=interval_hours)
    else:
        target = target_today
    return max((target - now).total_seconds(), 1.0)


async def _scheduler_loop() -> None:
    from config import (
        AUTO_REFRESH_ENABLED, AUTO_REFRESH_TIME,
        AUTO_REFRESH_INTERVAL_HOURS, AUTO_REFRESH_TIMEZONE,
        AUTO_REFRESH_ON_STARTUP,
    )
    if not AUTO_REFRESH_ENABLED:
        logger.info("[scheduler] AUTO_REFRESH_ENABLED=false，定时任务未启动")
        return

    logger.info(
        "[scheduler] 定时刷新已启动，计划时间 %s（%s），间隔 %sh",
        AUTO_REFRESH_TIME, AUTO_REFRESH_TIMEZONE, AUTO_REFRESH_INTERVAL_HOURS,
    )

    if AUTO_REFRESH_ON_STARTUP:
        logger.info("[scheduler] AUTO_REFRESH_ON_STARTUP=true，启动后立即执行一次")
        await _run_job()

    while True:
        secs = _seconds_to_next(
            AUTO_REFRESH_TIME, AUTO_REFRESH_INTERVAL_HOURS, AUTO_REFRESH_TIMEZONE
        )
        logger.info("[scheduler] 下次刷新将在 %.0f 秒后执行", secs)
        await asyncio.sleep(secs)
        await _run_job()


async def _run_job() -> None:
    """在线程池中执行同步的全量刷新任务，不阻塞事件循环。"""
    logger.info("[scheduler] 开始执行全量刷新任务")
    try:
        from database import engine
        from sqlmodel import Session
        from automation_service import run_all_users_job

        def _job():
            with Session(engine) as session:
                return run_all_users_job(session, triggered_by="scheduler")

        run = await asyncio.to_thread(_job)
        logger.info(
            "[scheduler] 全量刷新完成 status=%s users=%s/%s holdings=%s/%s",
            run.status, run.users_succeeded, run.users_total,
            run.holdings_updated, run.holdings_total,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[scheduler] 全量刷新任务异常: %s", exc)


def start() -> None:
    """在 FastAPI lifespan startup 时调用。"""
    global _task
    if _task is not None and not _task.done():
        return  # 已在运行，幂等
    _task = asyncio.ensure_future(_scheduler_loop())
    logger.info("[scheduler] 调度器 Task 已创建")


def stop() -> None:
    """在 FastAPI lifespan shutdown 时调用。"""
    global _task
    if _task and not _task.done():
        _task.cancel()
        logger.info("[scheduler] 调度器 Task 已取消")
    _task = None
