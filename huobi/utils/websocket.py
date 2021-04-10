# -*— coding:utf-8 -*-

"""
websocket接口封装

Author: QiaoXiaofeng
Date:   2020/01/08
History: 1.fix method locker bug when ws is disconnected.
"""

import json
import time
import traceback
import aiohttp
import asyncio

from huobi.const import *
from huobi.utils import logger
from huobi.config import config
from huobi.heartbeat import heartbeat

from huobi.utils.decorator import METHOD_LOCKERS


class Websocket:
    """ websocket接口封装
    """

    def __init__(self, url, check_conn_interval=10, send_hb_interval=10):
        """ 初始化
        @param url 建立websocket的地址
        @param check_conn_interval 检查websocket连接时间间隔
        @param send_hb_interval 发送心跳时间间隔，如果是0就不发送心跳消息
        """
        self._url = url
        self._check_conn_interval = check_conn_interval
        self._send_hb_interval = send_hb_interval
        self.ws = None  # websocket连接对象
        self.heartbeat_msg = None  # 心跳消息
        self.session = None

    def initialize(self):
        """ 初始化
        """
        # 注册服务 检查连接是否正常
        heartbeat.register(self._check_connection, self._check_conn_interval)
        # 注册服务 发送心跳
        if self._send_hb_interval > 0:
            heartbeat.register(self._send_heartbeat_msg, self._send_hb_interval)
        # 建立websocket连接
        asyncio.create_task(self._connect())

    async def close(self):
        self.closed = True
        await self.session.close()
        await self.ws.close()

    async def _connect(self):
        logger.info("url:", self._url, caller=self)
        METHOD_LOCKERS = {}
        proxy = config.proxy
        self.session = aiohttp.ClientSession()
        try:
            self.ws = await self.session.ws_connect(self._url, proxy=proxy)
            self.closed = False
        except aiohttp.ClientConnectionError:
            logger.error("connect to server error! url:", self._url, caller=self)
            return
        asyncio.create_task(self.connected_callback())
        asyncio.create_task(self.receive())

    async def _reconnect(self):
        """ 重新建立websocket连接
        """
        if self.closed:
            logger.info("websocket closed, not reconnecting", caller=self)
            return
    
        logger.warn("reconnecting websocket right now!", caller=self)
        await self._connect()

    async def connected_callback(self):
        """ 连接建立成功的回调函数
        * NOTE: 子类继承实现
        """
        pass

    async def receive(self):
        """ 接收消息
        """
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except:
                    data = msg.data
                await asyncio().create_task(self.process(data))
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await asyncio.create_task(self.process_binary(msg.data))
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.warn("receive event CLOSED:", msg, caller=self)
                await asyncio.create_task(self._reconnect())
            elif msg.type == aiohttp.WSMsgType.CLOSE:
                logger.warn("receive event CLOSE:", msg, caller=self)
                await asyncio.create_task(self._reconnect())
            elif msg.type == aiohttp.WSMsgType.CLOSING:
                logger.warn("receive event CLOSING:", msg, caller=self)
                await asyncio.create_task(self._reconnect())
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error("receive event ERROR:", msg, caller=self)
                await asyncio.create_task(self._reconnect())
            else:
                logger.warn("unhandled msg:", msg, caller=self)

    async def process(self, msg):
        """ 处理websocket上接收到的消息 text 类型
        * NOTE: 子类继承实现
        """
        raise NotImplementedError

    async def process_binary(self, msg):
        """ 处理websocket上接收到的消息 binary类型
        * NOTE: 子类继承实现
        """
        raise NotImplementedError

    async def _check_connection(self, *args, **kwargs):
        """ 检查连接是否正常
        """
        # 检查websocket连接是否关闭，如果关闭，那么立即重连
        if not self.ws or self.closed:
            logger.warn("websocket connection not connected yet!", caller=self)
            return
        if self.ws.closed:
            await asyncio.create_task(self._reconnect())
            return

    async def _send_heartbeat_msg(self, *args, **kwargs):
        """ 发送心跳给服务器
        """
        if not self.ws:
            logger.warn("websocket connection not connected yet!", caller=self)
            return
        if self.heartbeat_msg:
            try:
                if isinstance(self.heartbeat_msg, dict):
                    await self.ws.send_json(self.heartbeat_msg)
                elif isinstance(self.heartbeat_msg, str):
                    await self.ws.send_str(self.heartbeat_msg)
                else:
                    logger.error("send heartbeat msg failed! heartbeat msg:", self.heartbeat_msg, caller=self)
                    return
                logger.debug("send ping message:", self.heartbeat_msg, caller=self)
            except ConnectionResetError:
                traceback.print_exc()
                await asyncio.create_task(self._reconnect())


