#!/usr/bin/python
# -*- coding: UTF-8 -*-
# vim:set shiftwidth=2 tabstop=2 expandtab textwidth=79:

import logging
from spinbot.settings.settings import *

logging_format = "[%(asctime)s] %(process)d-%(levelname)s "
logging_format += "%(module)s::%(funcName)s():l%(lineno)d: "
logging_format += "%(message)s"

logging.basicConfig(
    format=logging_format,
    level=LOG_LEVEL
)

LOGGER = logging.getLogger()
