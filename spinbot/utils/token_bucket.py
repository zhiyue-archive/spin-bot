#!/usr/bin/python
# -*- coding: UTF-8 -*-
# vim:set shiftwidth=2 tabstop=2 expandtab textwidth=79:

# reference: https://github.com/bynil/v2ex-crawler/blob/f2ee091dff0207448f442a2f22c0d3af90dcdcac/token_bucket.py


import time


class Bucket(object):

    """
    traffic flow control with token bucket
    """

    update_interval = 30

    def __init__(self, rate=1, burst=None):
        self.rate = float(rate)
        if burst is None:
            self.burst = float(rate) * 10
        else:
            self.burst = float(burst)
        self.bucket = self.burst
        self.last_update = time.time()

    def get(self):
        """Get the number of tokens in bucket
        """
        now = time.time()
        if self.bucket >= self.burst:
            self.last_update = now
            return self.bucket
        # TODO:
        bucket = self.rate * (now - self.last_update)
        if bucket > 1:
            self.bucket += bucket
            if self.bucket > self.burst:
                self.bucket = self.burst
            self.last_update = now
        return self.bucket

    def set(self, value):
        """Set number of tokens in bucket
        """
        self.bucket = value

    def desc(self, value=1):
        """Use value tokens"""
        self.bucket -= value
