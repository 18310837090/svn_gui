#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker — 后台任务执行器（QThread + 信号）。

不用 QRunnable：PySide 6.11 中 QThreadPool.start() 会把 wrapper 所有权转给 C++，
任务一结束 QRunnable 的 C++ 对象连带成员 WorkerSignals 被析构，
后台线程再 emit 就报 "Signal source has been deleted"。
QThread 子类的所有权归 Python，无此问题。

用法:
    runner.run(fn, on_result=..., on_error=...)   # fn() 在后台线程执行
"""

from PySide6.QtCore import QThread, QObject, Signal


class Worker(QThread):
    result = Signal(object)
    error = Signal(object)
    finished_all = Signal()   # 自定义完成信号（QThread.finished 属于 C++，避免混淆）

    def __init__(self, fn, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            res = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            self.error.emit(e)
        else:
            self.result.emit(res)
        finally:
            self.finished_all.emit()


class TaskRunner(QObject):
    """单例式任务池：App 持有一个，所有页面共用。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keepalive = set()

    def run(self, fn, on_result=None, on_error=None, on_finished=None):
        w = Worker(fn, parent=self)
        if on_result:
            w.result.connect(on_result)
        if on_error:
            w.error.connect(on_error)
        if on_finished:
            w.finished_all.connect(on_finished)
        # 结束后从 keepalive 摘除（信号队列派发完才触发 finished）
        w.finished_all.connect(lambda _w=w: self._release(_w))
        self._keepalive.add(w)
        w.start()
        return w

    def _release(self, w):
        self._keepalive.discard(w)
        if w.isRunning():
            # finished_all 信号先于线程真正退出到达；等线程退出再销毁
            w.finished.connect(w.deleteLater)
        else:
            w.deleteLater()

    def shutdown(self, wait_ms=3000):
        """窗口关闭时调用: 等待所有后台线程收尾，避免 'Destroyed while running'"""
        for w in list(self._keepalive):
            w.wait(wait_ms)
        self._keepalive.clear()
