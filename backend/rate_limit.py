"""进程内轻量限流，不依赖 Redis。

用滑动窗口计数：在 window_seconds 内允许最多 max_calls 次调用。
超限时抛出 HTTP 429。
"""
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException

_store: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def check_rate_limit(key: str, max_calls: int, window_seconds: int) -> None:
    """超限时抛出 429，否则记录本次调用时间戳。"""
    now = time.monotonic()
    with _lock:
        # 清理窗口外的旧记录
        cutoff = now - window_seconds
        _store[key] = [t for t in _store[key] if t > cutoff]
        if len(_store[key]) >= max_calls:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        _store[key].append(now)
