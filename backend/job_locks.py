"""Single-process deployment: serialize writers of shared quotes and daily checkpoints."""
from functools import wraps
from threading import RLock

refresh_lock = RLock()


def serialized_refresh(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with refresh_lock:
            return fn(*args, **kwargs)
    return wrapped
