# -*- coding:utf-8 -*-
"""
极简做市策略，仅做演示使用

Author: Qiaoxiaofeng
Date:   2020/06/28
Email: andyjoe318@gmail.com
"""
# 策略实现
import time
from alpha import const
from alpha.utils import tools
from alpha.utils import logger
from alpha.config import config
from alpha.market import Market
from alpha.trade import Trade
from alpha.order import Order
from alpha.orderbook import Orderbook
from alpha.kline import Kline
from alpha.markettrade import Trade as MarketTrade
from alpha.asset import Asset
from alpha.position import Position
from alpha.error import Error
from alpha.tasks import LoopRunTask
from alpha.order import ORDER_ACTION_SELL, ORDER_ACTION_BUY, ORDER_STATUS_FAILED, ORDER_STATUS_CANCELED, ORDER_STATUS_FILLED,\
    ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET


class MyStrategy:

    def __init__(self):
        """ 初始化
        """
        self.strategy = config.strategy
        self.platform = config.accounts[0]["platform"]
        self.account = config.accounts[0]["account"]
        self.access_key = config.accounts[0]["access_key"]
        self.secret_key = config.accounts[0]["secret_key"]
        self.host = config.accounts[0]["host"]
        self.wss = config.accounts[0]["wss"]
        self.symbol = config.symbol
        self.channels = config.markets[0]["channels"]
        self.orderbook_length = config.markets[0]["orderbook_length"]
        self.orderbooks_length = config.markets[0]["orderbooks_length"]
        self.klines_length = config.markets[0]["klines_length"]
        self.trades_length = config.markets[0]["trades_length"]
        self.market_wss = config.markets[0]["wss"]

        self.orderbook_invalid_seconds = 100
        self.spread = 0.5 # 价差设定
        self.volume = 1 # 每次开仓数量

        self.last_bid_price = 0 # 上次的买入价格
        self.last_ask_price = 0 # 上次的卖出价格
        self.last_orderbook_timestamp = 0 # 上次的orderbook时间戳
        self.last_mark_price = 0 # 上次的标记价格

        self.raw_symbol = self.symbol.split('-')[0]
        self.partition_symbol = self.symbol.split('-')[1]

        self.ask1_price = 0
        self.bid1_price = 0
        self.ask1_volume = 0
        self.bid1_volume = 0

        self.mark_price = 0 # 标记价格

        # 交易模块
        cc = {
            "strategy": self.strategy,
            "platform": self.platform,
            "symbol": self.symbol,
            "account": self.account,
            "access_key": self.access_key,
            "secret_key": self.secret_key,
            "host": self.host,
            "wss": self.wss,
            "order_update_callback": self.on_event_order_update,
            "asset_update_callback": self.on_event_asset_update,
            "position_update_callback": self.on_event_position_update,
            "init_success_callback": self.on_event_init_success_callback,
        }
        self.trader = Trade(**cc)

        # 行情模块
        cc = {
            "platform": self.platform,
            "symbols": [self.symbol],
            "channels": self.channels,
            "orderbook_length": self.orderbook_length,
            "orderbooks_length": self.orderbooks_length,
            "klines_length": self.klines_length,
            "trades_length": self.trades_length,
            "wss": self.market_wss,
            "orderbook_update_callback": self.on_event_orderbook_update,
            "kline_update_callback": self.on_event_kline_update,
            "trade_update_callback": self.on_event_trade_update
        }
        self.market = Market(**cc)
        
        # 2秒执行1次
        LoopRunTask.register(self.on_ticker, 10)

        # TODO：delta对冲，可以使用现货或者期货进行delta对冲等操作。
        LoopRunTask.register(self.delta_hedging, 3600)

    async def on_ticker(self, *args, **kwargs):
        """ 定时执行任务
        """
        ts_diff = int(time.time()*1000) - self.last_orderbook_timestamp
        if ts_diff > self.orderbook_invalid_seconds * 1000:
            logger.warn("received orderbook timestamp exceed:", self.strategy, self.symbol, ts_diff, caller=self)
            return

        # 获取标记价格，每次的挂单价格与指数价格进行比较。
        success, error = await self.trader.rest_api.get_market_index(contract_code=self.symbol)
        if error: 
            logger.error("Get swap market index faild:", error, caller=self)
        else:
            for item in success["data"]:
                if item["contract_code"] == self.symbol:
                    self.mark_price = item["mark_price"]

        await self.cancel_orders()
        await self.place_orders()

    async def cancel_orders(self):
        """  取消订单
        """
        order_nos = [ orderno for orderno in self.trader.orders ]
        #if order_nos and self.last_mark_price != self.mark_price:
        if order_nos:
            _, errors = await self.trader.revoke_order(*order_nos)
            if errors:
                logger.error(self.strategy,"cancel future order error! error:", errors, caller=self)
            else:
                logger.info(self.strategy,"cancel future order:", order_nos, caller=self)
    
    async def place_orders(self):
        """ 下单
        """
        orders_data = []
        if self.trader.position and self.trader.position.short_quantity:
            # 平空单
            price = round(self.mark_price - self.spread, 1)
            quantity = -self.trader.position.short_quantity
            action = ORDER_ACTION_BUY
            new_price = str(price)  # 将价格转换为字符串，保持精度
            if quantity:
                orders_data.append({"price": new_price, "quantity": quantity, "action": action, "order_type": ORDER_TYPE_LIMIT })
                self.last_mark_price = self.mark_price
        if self.trader.position and self.trader.position.long_quantity:
            # 平多单
            price = round(self.mark_price + self.spread, 1)
            quantity = self.trader.position.long_quantity
            action = ORDER_ACTION_SELL
            new_price = str(price)  # 将价格转换为字符串，保持精度
            if quantity:
                orders_data.append({"price": new_price, "quantity": quantity, "action": action, "order_type": ORDER_TYPE_LIMIT })
                self.last_mark_price = self.mark_price
        if self.trader.assets and self.trader.assets.assets.get(self.raw_symbol).get("free"):
            # 开空单
            price = round(self.bid1_price + self.spread, 1)
            volume = 1 
            if volume >= 1:
                quantity = - volume #  空1张
                action = ORDER_ACTION_SELL
                new_price = str(price)  # 将价格转换为字符串，保持精度
                if quantity:
                    orders_data.append({"price": new_price, "quantity": quantity, "action": action, "order_type": ORDER_TYPE_LIMIT })
                    self.last_mark_price = self.mark_price

        # if self.trader.assets and self.trader.assets.assets.get(self.partition_symbol).get("free"):
            # 开多单
            price = round(self.bid1_price - self.spread, 1)
            volume = 1 
            if volume >= 1:
                quantity = volume #  多1张
                action = ORDER_ACTION_BUY
                new_price = str(price)  # 将价格转换为字符串，保持精度
                if quantity:
                    orders_data.append({"price": new_price, "quantity": quantity, "action": action, "order_type": ORDER_TYPE_LIMIT })
                    self.last_mark_price = self.mark_price

        if orders_data:
            order_nos, error = await self.trader.create_orders(orders_data)
            if error:
                logger.error(self.strategy, "create future order error! error:", error, caller=self)
            logger.info(self.strategy, "create future orders success:", order_nos, caller=self)

    async def delta_hedging(self, *args, **kwargs):
        """ delta hedge
        """
        logger.debug("delta hedging", caller=self)
        o_delta = 0
        assets, error = await self.trader.rest_api.get_asset_info(self.raw_symbol)
        for item in assets:
            if item["symbol"] == self.raw_symbol:
                o_delta = item["delta"]
                o_gamma = item["gamma"]
                o_theta = item["theta"]
                o_vega = item["vega"]
        #TODO: 增加delta对冲，现货或者期货对冲。 

    async def on_event_orderbook_update(self, orderbook: Orderbook):
        """  orderbook更新
            self.market.orderbooks 是最新的orderbook组成的队列，记录的是历史N次orderbook的数据。
            本回调所传的orderbook是最新的单次orderbook。
        """
        logger.debug("orderbook:", orderbook, caller=self)
        if orderbook.asks:
            self.ask1_price = float(orderbook.asks[0][0])  # 卖一价格
            self.ask1_volume = float(orderbook.asks[0][1])  # 卖一数量
        if orderbook.bids:
            self.bid1_price = float(orderbook.bids[0][0])  # 买一价格
            self.bid1_volume = float(orderbook.bids[0][1])  # 买一数量
        self.last_orderbook_timestamp = orderbook.timestamp

    async def on_event_order_update(self, order: Order):
        """ 订单状态更新
        """
        logger.info("order update:", order, caller=self)

    async def on_event_asset_update(self, asset: Asset):
        """ 资产更新
        """
        logger.info("asset update:", asset, caller=self)

    async def on_event_position_update(self, position: Position):
        """ 仓位更新
        """
        logger.info("position update:", position, caller=self)
    
    async def on_event_kline_update(self, kline: Kline):
        """ kline更新
            self.market.klines 是最新的kline组成的队列，记录的是历史N次kline的数据。
            本回调所传的kline是最新的单次kline。
        """
        logger.debug("kline update:", kline, caller=self)
    
    async def on_event_trade_update(self, trade: MarketTrade):
        """ market trade更新
            self.market.trades 是最新的逐笔成交组成的队列，记录的是历史N次trade的数据。
            本回调所传的trade是最新的单次trade。
        """
        logger.debug("trade update:", trade, caller=self)
    
    async def on_event_init_success_callback(self, success: bool, error: Error, **kwargs):
        """ init success callback
        """
        logger.debug("init success callback update:", success, error, kwargs, caller=self)
