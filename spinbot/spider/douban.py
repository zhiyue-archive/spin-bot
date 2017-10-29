#!/usr/bin/python
# -*- coding: UTF-8 -*-
# vim:set shiftwidth=2 tabstop=2 expandtab textwidth=79:
import asyncio
import json
import logging
import os
import random
import string
from collections import namedtuple

import aiohttp
import async_timeout
import lxml
import requests
import uvloop
from lxml import html

logging.basicConfig(
  level=logging.DEBUG
)
logger = logging.getLogger('douban')

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36'

proxies = {
  'https': 'http://spin.printf.me:3128',
}

UserMeta = namedtuple('UserMeta', 'home_url name')
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
loop = asyncio.get_event_loop()
sema = asyncio.Semaphore(15, loop=loop)
users = set()
# proxies = requests.get('http://spin.printf.me:8000/?types=0&country=国内&count=10')
# ip_ports = json.loads(proxies.text)


# sema = asyncio.BoundedSemaphore(100)

def get_data(filename, default=''):
  """
  Get data from a file
  :param filename: filename
  :param default: default value
  :return: data
  """
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
    data = [default]
  return data


def get_random_user_agent():
  """
  Get a random user agent string.
  :return: Random user agent string.
  """
  return random.choice(get_data('user_agents.txt', USER_AGENT))


async def fetch(url):
  try:
    with async_timeout.timeout(15):
      headers = {'User-Agent': get_random_user_agent(),
                 'Host': 'www.douban.com'}
      cookies = {
        'bid': "".join(random.sample(string.ascii_letters + string.digits, 11))}
      async with aiohttp.request(
        method='GET',
        url=url, headers=headers,
        cookies=cookies,
        proxy='http://spin.printf.me:3128', allow_redirects=False) as r:
        data = await r.text()
        return data
  except Exception as e:
    # logger.exception(e)
    data = await fetch(url)
    return data


async def fetch_use_session(url):
  try:
    with (await sema):
      with async_timeout.timeout(15):
        headers = {'User-Agent': get_random_user_agent(),
                   'Host': 'www.douban.com'}
        cookies = {
          'bid': "".join(random.sample(string.ascii_letters + string.digits, 11))}
        async with aiohttp.ClientSession(cookies=cookies) as session:
          # random.shuffle(ip_ports)
          # ip = ip_ports[0][0]
          # port = ip_ports[0][1]
          # proxy = 'http://{ip}:{port}'.format(ip=ip, port=port)
          # logger.info('proxy is:{}, url is:{}'.format(proxy, url))
          async with session.get(
            url=url, headers=headers,
            proxy='http://spin.printf.me:3128',
            allow_redirects=False) as r:
            logger.info('status is : {}, type is : {}'.format(
              r.status, type(r.status)))
            if r.status == 200:
              data = await r.text()
              logger.info('success download url:{}'.format(url))
              return data
  except Exception as e:
    # logger.exception(e)
    data = await fetch_use_session(url)
    return data

  logger.error('Error status code {}, url is : {}'.format(
    r.status, url))
  return await fetch_use_session(url)


async def get_member(url):

  try:
    r = await fetch_use_session(url)
  except Exception as e:
    logger.exception(e)
    return

  tree = html.fromstring(r)
  group_users = tree.cssselect('.nbg')
  if len(group_users) == 0:
    logger.error('Group Users is zero. data:{}'.format(r))
    return await get_member(url)
  for user_ in group_users:
    user_meta = UserMeta(user_.attrib['href'],
                         user_.cssselect('img')[0].attrib['alt'])
    users.add(user_meta)

  logger.info('Finish get members of url: {}, members numbers is: {}'.format(
    url, len(users)))


async def get_max_page(group_id):
  step = 35
  group_url = 'https://www.douban.com/group/{}/members'.format(group_id)
  rsp = await fetch_use_session(group_url)
  tree = lxml.html.fromstring(rsp)
  try:
    total_amount = int(tree.cssselect('.ft-members i')[0].text)
    page_num = int(total_amount / step) + 1
    logger.info('The number of Group:{} is {}'.format(group_id, page_num))
  except Exception as e:
    logger.exception(e)
    logger.info(rsp)
    return await get_max_page(group_id)
  return page_num


async def fetch_group_members_page(max_page, loop):
  step = 35
  members_url = 'https://www.douban.com/group/{}/members?start={}'
  tasks = []
  for index in range(max_page):
    # task = asyncio.ensure_future(
    #   )
    task = loop.create_task(
      get_member(members_url.format(group_id, index * step)))
    tasks.append(task)

  await asyncio.gather(*tasks, loop=loop)


async def get_group_members(group_id, loop):
  max_page_num = await get_max_page(group_id)
  result = await fetch_group_members_page(max_page_num, loop)


def run(group_id):
  task = asyncio.ensure_future(get_group_members(group_id, loop))
  loop.run_until_complete(task)


if __name__ == '__main__':
  group_id = 10021
  run(group_id)
