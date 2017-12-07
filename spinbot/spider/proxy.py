#!/usr/bin/env python3.4
# -*- coding: UTF-8 -*-
# vim:set shiftwidth=2 tabstop=2 expandtab textwidth=79:

from spinbot.settings import *
from spinbot.database.redis.redisbase import RedisSession
from spinbot.utils.token_bucket import Bucket
import datetime
from collections import defaultdict
import random
import requests
import logging
import time

logger = logging.getLogger(__name__)

UPSTREAM_URL = 'http://127.0.0.1:5010/get_all/'


class ProxyPool:
  @property
  def redis_session(self):
    redis_client = RedisSession()
    redis_session = redis_client.get_redis_pool()
    return redis_session


class ProxyMixin:
  def __init__(self, upstream_url=None, min_count=10, max_fail=4, rate=2,
               burst=1, update_interval=30, *args, **kwargs):
    self.upstream_url = UPSTREAM_URL
    self.proxy_pool = defaultdict(dict)
    self.deleted_proxies = set()
    self.min_count = CRAWLER_SETTINGS.get('max_tasks')
    self.rate = rate
    self.burst = burst
    self.valid_proxy_count = 0
    self.last_update = time.time()
    self.last_clear = time.time()
    self.update_interval = update_interval * 60
    self.clear_interval = 6 * 3600
    if min_count:
      self.min_count = min_count
    self.max_fail = max_fail

    if upstream_url:
      self.upstream_url = upstream_url

    self._fetch_proxy_from_upstream()

  @property
  def proxy(self):
    if self.valid_proxy_count < self.min_count:
      self._fetch_proxy_from_upstream()
    proxy = self.get_proxy()
    logger.info('proxy ip: %s', proxy)
    return proxy

  def get_proxy(self):
    logger.info('valid ip number is: {}'.format(self.valid_proxy_count))
    now = time.time()
    if now - self.last_update > self.update_interval:
      self._fetch_proxy_from_upstream()
    while True:
      ip, value = random.choice(list(self.proxy_pool.items()))
      if value['fail'] > self.max_fail:
        self.delete_proxy(ip)
        continue
      bucket = value.get('bucket')
      if bucket:
        if bucket.get() < 1:
          continue
        bucket.desc()
      return 'http://{}'.format(ip.strip())

  def clear_fail_proxy(self):
    for k, v in self.proxy_pool.items():
      if v.get('fail') > self.max_fail:
        del self.proxy_pool[k]
        self.deleted_proxies.add(k)

  def update_fail_proxy(self, ip):
    ip = ip.split('//')[-1]
    value = self.proxy_pool.get(ip, {
      'bucket': Bucket(rate=self.rate, burst=self.burst),
      'fail': 0,
    })
    value['fail'] = value.get('fail', 0) + 1
    self.proxy_pool.update({ip: value})

  def delete_proxy(self, ip):
    ip = ip.split('//')[-1]
    del self.proxy_pool[ip]
    self.valid_proxy_count -= 1
    self.deleted_proxies.add(ip)
    if self.valid_proxy_count < self.min_count:
      self._fetch_proxy_from_upstream()

  def clear_deleted_proxy(self):
    self.deleted_proxies.clear()
    self.last_clear = time.time()

  def _fetch_proxy_from_upstream(self):
    r = requests.get(self.upstream_url)
    ips = r.json()
    now = time.time()
    if now - self.last_clear > self.clear_interval:
      self.clear_deleted_proxy()
    self.clear_fail_proxy()
    for ip in ips:
      if ip.strip() not in self.proxy_pool.keys() and ip.strip() not in self.deleted_proxies:
        self.proxy_pool[ip] = {
          'bucket': Bucket(rate=self.rate, burst=self.burst),
          'fail': 0
        }
    self.valid_proxy_count = len(self.proxy_pool)
    self.last_update = time.time()
