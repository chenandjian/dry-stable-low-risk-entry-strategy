# scanner/data_source.py
import threading
import logging

logger = logging.getLogger(__name__)


class DataSourceManager:
    """管理多个数据源的互斥访问。

    每个数据源同一时间只能被一个线程使用。
    使用 threading.Lock 实现非阻塞互斥。
    """

    def __init__(self):
        self._locks: dict[str, threading.Lock] = {
            "baidu": threading.Lock(),
            "sina": threading.Lock(),
            "tencent": threading.Lock(),
        }

    def acquire(self, ds_name: str) -> bool:
        """非阻塞尝试获取数据源锁。成功返回 True，已被占用返回 False。"""
        lock = self._locks.get(ds_name)
        if lock is None:
            logger.warning(f"Unknown data source: {ds_name}")
            return False
        return lock.acquire(blocking=False)

    def release(self, ds_name: str):
        """释放数据源锁。重复释放安全。"""
        lock = self._locks.get(ds_name)
        if lock is None:
            return
        try:
            lock.release()
        except RuntimeError:
            pass  # 锁未被持有，忽略

    def try_acquire_any(self) -> str | None:
        """尝试获取任意一个空闲数据源，返回数据源名称。
        如果全部被占用，返回 None。
        源顺序随机化，避免低并发时总抢同一个源。"""
        import random
        names = list(self._locks.keys())
        random.shuffle(names)
        for name in names:
            if self.acquire(name):
                return name
        return None

    def is_available(self, ds_name: str) -> bool:
        """检查数据源是否空闲（不获取锁）。"""
        lock = self._locks.get(ds_name)
        if lock is None:
            return False
        return lock.locked() is False
