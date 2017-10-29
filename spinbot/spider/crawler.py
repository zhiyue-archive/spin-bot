import asyncio
import cgi
import json
import logging
import os
import random
import string
import urllib
import urllib.parse
import re
import time
from collections import namedtuple

import aiohttp
import async_timeout
import lxml
import requests
import uvloop
from lxml import html
try:
    # Python 3.4.
    from asyncio import JoinableQueue as Queue
except ImportError:
    # Python 3.5.
    from asyncio import Queue

logging.basicConfig(
  level=logging.DEBUG
)
logger = logging.getLogger(__name__)

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36'


def lenient_host(host):
  parts = host.split('.')[-2:]
  return ''.join(parts)

def is_redirect(response):
  return response.status in (300, 301, 302, 303, 307)

FetchStatistic = namedtuple('FetchStatistic',
                            ['url',
                             'next_url',
                             'status',
                             'exception',
                             'size',
                             'content_type',
                             'encoding',
                             'num_urls',
                             'num_new_urls'])


def get_user_agents(filename):
  try:
    root_folder = os.path.dirname(os.path.dirname(__file__))
  except:
    root_folder = os.path.curdir
  user_agents_file = os.path.join(
    os.path.join(root_folder, 'data'), filename)
  try:
    with open(user_agents_file) as fp:
      data = [_.strip() for _ in fp.readlines()]
  except:
    data = None
  return data



class BaseCrawler(object):

  USER_AGENTS = ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36']
  ALLOW_CONTENT_TYPE = ('text/html', 'application/xml')

  def __init__(self, roots, exclude=None, strict=True, max_redirect=10, proxy=None,
               max_tries=4, user_agents=None, max_tasks=10, time_out=15, *, loop=None):
    if not loop:
      asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
      self.loop = asyncio.get_event_loop()
    else:
      self.loop = loop
    self.roots = roots
    self.exclude = exclude
    self.strict = strict
    self.max_redirect = max_redirect
    self.proxy = proxy
    self.max_tries = max_tries
    self.max_tasks = max_tasks
    self.time_out = time_out
    self.q = Queue(loop=self.loop)
    self.seen_urls = set()
    self.done = []
    self._session = aiohttp.ClientSession(loop=self.loop)
    self.root_domains = set()
    for root in roots:
      parts = urllib.parse.urlparse(root)
      host, port = urllib.parse.splitport(parts.netloc)
      if not host:
        continue
      if re.match(r'\A[\d\.]*\Z', host):
        self.root_domains.add(host)
      else:
        host = host.lower()
        if self.strict:
          self.root_domains.add(host)
        else:
          self.root_domains.add(lenient_host(host))
    # from ipdb import set_trace; set_trace()
    for root in roots:
      self.add_url(root)

    self.user_agents = self.USER_AGENTS
    if user_agents:
      self._user_agents = user_agents
    self.t0 = time.time()
    self.t1 = None

  @property
  def session(self):
    if not self._session:
      self._session = aiohttp.ClientSession(loop=self.loop)
    return self._session

  def host_okay(self, host):
    """Check if a host should be crawled.
    A literal match (after lowercasing) is always good.  For hosts
    that don't look like IP addresses, some approximate matches
    are okay depending on the strict flag.
    """
    host = host.lower()
    if host in self.root_domains:
      return True
    if re.match(r'\A[\d\.]*\Z', host):
      return False
    if self.strict:
      return self._host_okay_strictish(host)
    return self._host_okay_lenient(host)

  def _host_okay_strictish(self, host):
      """Check if a host should be crawled, strict-ish version.
      This checks for equality modulo an initial 'www.' component.
      """
      host = host[4:] if host.startswith('www.') else 'www.' + host
      return host in self.root_domains

  def _host_okay_lenient(self, host):
      """Check if a host should be crawled, lenient version.
      This compares the last two components of the host.
      """
      return lenient_host(host) in self.root_domains

  def record_statistic(self, fetch_statistic):
      """Record the FetchStatistic for completed / failed URL."""
      self.done.append(fetch_statistic)

  def get_random_user_agent(self):
    if len(self._user_agents) == 1:
      return self._user_agents
    return random.choice(self._user_agents)

  def close(self):
    self.session.close()

  def add_url(self, url, max_redirect=None, meta=None):
    if meta is None:
      meta = {}
    if max_redirect is None:
      max_redirect = self.max_redirect
    logger.debug('adding %r %r', url, max_redirect)
    self.seen_urls.add(url)
    self.q.put_nowait((url, max_redirect, meta))

  def parse_item(self, url, data):
    pass

  async def parse(self, url, response, **kwargs):
    links = set()
    content_type = None
    encoding = None
    body = await response.read()

    if response.status == 200:
      content_type = response.headers.get('content-type')
      pdict = {}

      if content_type:
        content_type, pdict = cgi.parse_header(content_type)

      encoding = pdict.get('charset', 'utf-8')
      if content_type in self.ALLOW_CONTENT_TYPE:
        data = await response.text()
        # from ipdb import set_trace; set_trace()
        links = await self._parse_links(response.url, data)
        self.parse_item(url, data)

    stat = FetchStatistic(
      url=response.url.human_repr(),
      next_url=None,
      status=response.status,
      exception=None,
      size=len(body),
      content_type=content_type,
      encoding=encoding,
      num_urls=len(links),
      num_new_urls=len(links - self.seen_urls))
    return stat, links

  async def _parse_links(self, base_url, text):
    links = set()

    # Replace href with (?:href|src) to follow image links.
    urls = set(re.findall(r'''(?i)href=["']([^\s"'<>]+)''',
                          text))
    if urls:
      logger.info('got %r distinct urls from %r',
                  len(urls), base_url)
    for url in urls:
      try:
        normalized = urllib.parse.urljoin(base_url.human_repr(), url)
        # normalized = base_url.join(url)
        defragmented, frag = urllib.parse.urldefrag(normalized)
      except TypeError as type_error:
        logger.error('join error happen on base_url: %r, url: %r',
                     base_url, url)
        continue
      if self.url_allowed(defragmented):
        links.add(defragmented)
    return links

  def _get_headers(self, **kwargs):
    headers = {
      'User-Agent': self.get_random_user_agent()
    }
    headers.update(**kwargs)
    return headers

  async def fetch(self, url, max_redirect, meta=None):
    tries = 0
    exception = None
    while tries < self.max_tries:
      try:
        with async_timeout.timeout(self.time_out):
          headers = self._get_headers()
          response = await self.session.get(
            url, headers=headers, proxy=self.proxy, allow_redirects=False)

          if tries > 1:
            logger.info('try %r for %r success', tries, url)

          break
      except aiohttp.ClientError as client_error:
        logger.info('try %r for %r raised %r', tries, url, client_error)
        exception = client_error
      except asyncio.TimeoutError as timeout_error:
        logger.info('try %r for %r raised %r', tries, url, timeout_error)
        exception = timeout_error
      except Exception as e:
        logger.info('try %r for %r raised %r', tries, url, e)
        exception = e

      tries += 1
    else:
      # We never broke out of the loop: all tries failed.
      logger.error('%r failed after %r tries',
                   url, self.max_tries)
      self.record_statistic(FetchStatistic(url=url,
                                           next_url=None,
                                           status=None,
                                           exception=exception,
                                           size=0,
                                           content_type=None,
                                           encoding=None,
                                           num_urls=0,
                                           num_new_urls=0))
      return

    try:
      if is_redirect(response):
        location = response.headers['location']
        next_url = urllib.parse.urljoin(url, location)
        self.record_statistic(FetchStatistic(url=url,
                                             next_url=next_url,
                                             status=response.status,
                                             exception=None,
                                             size=0,
                                             content_type=None,
                                             encoding=None,
                                             num_urls=0,
                                             num_new_urls=0))

        if next_url in self.seen_urls:
          return
        if max_redirect > 0:
          logger.info('redirect to %r from %r', next_url, url)
          self.add_url(next_url, max_redirect - 1)
        else:
          logger.error('redirect limit reached for %r from %r',
                       next_url, url)
      else:
        stat, links = await self.parse(url, response)
        self.record_statistic(stat)
        for link in links.difference(self.seen_urls):
          self.add_url(link, meta=meta)
        self.seen_urls.update(links)
    finally:
      await response.release()

  async def work(self):
    try:
      while True:
        url, max_redirect, meta = await self.q.get()
        assert url in self.seen_urls
        await self.fetch(url, max_redirect, meta)
        self.q.task_done()
    except asyncio.CancelledError:
      pass

  def url_allowed(self, url):
    if self.exclude and re.search(self.exclude, url):
      return False
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ('http', 'https'):
      logger.debug('skipping non-http scheme in %r', url)
      return False
    host, port = urllib.parse.splitport(parts.netloc)
    if not self.host_okay(host):
      logger.debug('skipping non-root host in %r', url)
      return False
    return True

  async def crawl(self):
    workers = [asyncio.Task(self.work(), loop=self.loop)
               for _ in range(self.max_tasks)]

    self.t0 = time.time()
    await self.q.join()
    self.t1 = time.time()
    for w in workers:
      w.cancel()


class DoubanGroupUserCrawler(BaseCrawler):

  ALLOWED_PATH = [r'/group/\w+/members', r'/group/\w+',]
  ITEM_PATH = {'group': r'/group/\w+/members'}
  UserMeta = namedtuple('UserMeta', 'home_url name')
  Group_BASE_URL = 'https://www.douban.com/group/{}/members'

  def __init__(self, roots, exclude=None, strict=True, max_redirect=10,
               proxy=None, max_tries=4, user_agents=None, max_tasks=10,
               time_out=15, allowed_paths=None, item_paths=None,
               group_ids=None, *, loop=None):
    super(DoubanGroupUserCrawler, self).__init__(
      roots, exclude, strict, max_redirect, proxy,max_tries, user_agents,
      max_tasks, time_out, loop=loop)
    self.allowed_paths = self.ALLOWED_PATH
    if allowed_paths:
      self.allowed_paths = allowed_paths
    self.item_paths = self.ITEM_PATH
    if item_paths:
      self.item_paths = item_paths
    self.users = set()
    self.grou_ids = group_ids
    self.init_roots()

  def init_roots(self):
    self.root_domains.add(self.Group_BASE_URL)
    if self.grou_ids:
      for gid in self.grou_ids:
        root_url = self.Group_BASE_URL.format(gid)
        self.add_url(root_url)


  @property
  def session(self):
    if not self._session:
      self._session = aiohttp.ClientSession(loop=self.loop)
    cookies = {'bid': DoubanGroupUserCrawler.get_bid_of_cookies()}
    self._session.cookie_jar.update_cookies(cookies)
    return self._session

  @classmethod
  def get_bid_of_cookies(cls):
    return ''.join(random.sample(string.ascii_letters + string.digits, 11))


  def _get_headers(self, **kwargs):
    headers = super(DoubanGroupUserCrawler, self)._get_headers()
    headers.update({'Host': 'www.douban.com'})
    return headers

  def get_parse_function(self, name):
    parse_function_name = 'parse_{}'.format(name)
    if hasattr(self, parse_function_name):
      return getattr(self, parse_function_name)
    logger.error('Not Implemented method: %r', parse_function_name)
    raise NotImplementedError

  def parse_group(self, url, data):
    tree = html.fromstring(data)
    group_users = tree.cssselect('.nbg')
    if len(group_users) == 0:
      logger.error('Group Users is zero. data:{}'.format(data))
    for user_ in group_users:
      user_meta = self.UserMeta(user_.attrib['href'],
                           user_.cssselect('img')[0].attrib['alt'])
      self.users.add(user_meta)

    logger.info('Finish get members of url: {}, members numbers is: {}'.format(
      url, len(self.users)))

  def parse_item(self, url, data):
    allowed, parse_function = self.parse_item_allowed(url)
    if allowed:
     parse_function(url, data)

  def parse_item_allowed(self, url):
    if self.item_paths:
      for key, rule in self.item_paths.items():
        if not re.search(rule, url):
          continue
        return True, self.get_parse_function(key)
    return False, None

  def path_allowed(self, url):
    if self.allowed_paths:
      for rule in self.allowed_paths:
        if not re.search(rule, url):
          continue
        return True
    return False


  def url_allowed(self, url):
    allowed = super(DoubanGroupUserCrawler, self).url_allowed(url)
    if allowed:
      return self.path_allowed(url)
    return False


