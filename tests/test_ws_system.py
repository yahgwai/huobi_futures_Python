import sys
import unittest
from config import *
import time

sys.path.append('..')
from huobi.platforms.huobi_usdt_swap.logger import *
from huobi.platforms.huobi_usdt_swap.ws_system import *


class TestWsSystem(unittest.TestCase):
    def _callback(self, jdata):
        logger.info('_callback:{}'.format(jdata))

    def test_sub(self):
        ws = WsSystem()
        data = {"op": "sub", "topic": "public.linear-swap.heartbeat"}
        ws.sub(data, self._callback)

        time.sleep(60)
        ws.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
