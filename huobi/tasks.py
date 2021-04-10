# -*- coding:utf-8 -*-

"""
Tasks module.
1. Register a loop run task:
    a) assign a asynchronous callback function;
    b) assign a execute interval time(seconds), default is 1s.
    c) assign some input params like `*args, **kwargs`;
2. Register a single task to run:
    a) Create a coroutine and execute immediately.
    b) Create a coroutine and delay execute, delay time is seconds, default delay time is 0s.

Author: HuangTao
Date:   2018/04/26
Email:  huangtao@ifclover.com
"""

import asyncio
import inspect

from huobi.heartbeat import heartbeat

__all__ = ("LoopRunTask", "SingleTask")


class LoopRunTask(object):
    """ Loop run task.
    """

    @classmethod
    def register(cls, func, interval=1, *args, **kwargs):
        """ Register a loop run.

        Args:
            func: Asynchronous callback function.
            interval: execute interval time(seconds), default is 1s.

        Returns:
            task_id: Task id.
        """
        task_id = heartbeat.register(func, interval, *args, **kwargs)
        return task_id

    @classmethod
    def unregister(cls, task_id):
        """ Unregister a loop run task.

        Args:
            task_id: Task id.
        """
        heartbeat.unregister(task_id)


class SingleTask:
    """ Single run task.
    """

    @classmethod
    def run(cls, func, *args, **kwargs):
        """ Create a coroutine and execute immediately.

        Args:
            func: Asynchronous callback function.
        """
        asyncio.create_task(func(*args, **kwargs))

    async def _wait_and_call(self, delay, func, *args, **kwargs):
        await asyncio.sleep(delay)
        await asyncio.create_task(func(*args, **kwargs))

    @classmethod
    def call_later(cls, func, delay=0, *args, **kwargs):
        """ Create a coroutine and delay execute, delay time is seconds, default delay time is 0s.

        Args:
            func: Asynchronous callback function.
            delay: Delay time is seconds, default delay time is 0, you can assign a float e.g. 0.5, 2.3, 5.1 ...
        """
        if not inspect.iscoroutinefunction(func):
            asyncio.create_task(cls._wait_and_call(delay, func, args, kwargs))
        else:
            def foo(f, *args, **kwargs):
                asyncio.create_task(f(*args, **kwargs))
            asyncio.create_task(cls._wait_and_call(delay, foo, func, *args))
