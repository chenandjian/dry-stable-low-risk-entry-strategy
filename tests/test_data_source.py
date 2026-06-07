# tests/test_data_source.py
import pytest
import threading
import time
from scanner.data_source import DataSourceManager


def test_acquire_release_single_source():
    """获取和释放单个数据源"""
    mgr = DataSourceManager()
    assert mgr.acquire("sina") is True
    assert mgr.acquire("sina") is False  # 已被占用
    mgr.release("sina")
    assert mgr.acquire("sina") is True   # 释放后可获取
    mgr.release("sina")


def test_two_sources_independent():
    """两个数据源互不影响"""
    mgr = DataSourceManager()
    assert mgr.acquire("sina") is True
    assert mgr.acquire("tencent") is True  # 不同源，不冲突
    mgr.release("sina")
    mgr.release("tencent")


def test_try_acquire_any():
    """自动获取空闲数据源"""
    mgr = DataSourceManager()
    ds = mgr.try_acquire_any()
    assert ds in ("baidu", "sina", "tencent")
    ds2 = mgr.try_acquire_any()
    assert ds2 in ("baidu", "sina", "tencent")
    assert ds2 != ds  # 第二个源不同于第一个
    ds3 = mgr.try_acquire_any()
    assert ds3 in ("baidu", "sina", "tencent")
    assert ds3 not in (ds, ds2)  # 第三个源不同于前两个
    assert mgr.try_acquire_any() is None  # 三个都忙
    mgr.release(ds)
    mgr.release(ds2)
    mgr.release(ds3)


def test_release_always_safe():
    """重复释放不会崩溃"""
    mgr = DataSourceManager()
    mgr.acquire("sina")
    mgr.release("sina")
    mgr.release("sina")  # 不抛异常
    mgr.release("nonexistent")  # 不抛异常


def test_concurrent_access():
    """并发场景：两个线程各取一个源"""
    mgr = DataSourceManager()
    results = []

    def worker(name):
        ds = mgr.try_acquire_any()
        if ds:
            results.append((name, ds))
            time.sleep(0.05)  # 模拟工作
            mgr.release(ds)

    t1 = threading.Thread(target=worker, args=("t1",))
    t2 = threading.Thread(target=worker, args=("t2",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    sources = [r[1] for r in results]
    assert len(sources) == 2
    assert sources[0] != sources[1]  # 不会同时用同一个源
