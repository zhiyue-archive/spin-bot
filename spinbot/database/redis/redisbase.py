import asyncio
import aioredis

from spinbot.settings import REDIS_SETTING
from spinbot.utils import singleton

@singleton
class RedisSession:
  _pool = None

  async def get_redis_pool(self):
    if not self._pool:
      if not REDIS_SETTING:
        self._pool = await aioredis.create_pool('redis://localhost', minsize=5,
                                                maxsize=10)
      else:
        self._pool = await aioredis.create_pool(
          'redis://{}'.format(REDIS_SETTING.get('HOST'), 'localhost'),
          db=REDIS_SETTING.get('DB', None),
          minsize=REDIS_SETTING.get('POOLSIZE', 5),
          maxsize=REDIS_SETTING.get('POOLSIZE', 5) + 10)

    return self._pool
