#!/usr/bin/python
# -*- coding: UTF-8 -*-
# vim:set shiftwidth=2 tabstop=2 expandtab textwidth=79:
import os
import logging

MOTOR_URI = 'mongodb://127.0.0.1:27017/douban'
MONGODB = dict(
  MONGO_HOST=os.getenv('MONGO_HOST', ""),
  MONGO_PORT=os.getenv('MONGO_PORT', 27017),
  MONGO_USERNAME=os.getenv('MONGO_USERNAME', ""),
  MONGO_PASSWORD=os.getenv('MONGO_PASSWORD', ""),
  DATABASE='owllook',
)

LOG_LEVEL = logging.DEBUG

# crawler settings
CRAWLER_SETTINGS = {
  'max_tries': 10,
  'max_tasks': 50,
}



try:
    from spinbot.settings.settings_local import *
except ImportError as e:
    pass
