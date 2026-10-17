"""Minitel-side modem simulator (opposite roles of minitel_modem.v23)."""
import math
from collections import deque

import numpy as np

from minitel_modem.v23 import FskDemod, Uart7E1, frame_7e1, FS


class MinitelSim:
    def __init__(self, level=3000):
        self.level = level
        self.bits = deque()
        self.phase, self.rem, self.cur, self.on = 0.0, 0.0, 1, False
        self.demod = FskDemod(1700, cutoff=700, ntaps=41, smooth=2)
        self.uart = Uart7E1(1200)
        self.screen = bytearray()

    def type(self, data):
        for b in data:
            self.bits.extend(frame_7e1(b))

    def generate(self, n):
        out = np.zeros(n)
        if not self.on:
            return out.astype(np.int16)
        spb = FS / 75
        for i in range(n):
            if self.rem <= 0:
                self.cur = self.bits.popleft() if self.bits else 1
                self.rem += spb
            self.rem -= 1
            self.phase += 2 * math.pi * (390 if self.cur else 450) / FS
            out[i] = math.sin(self.phase)
        return (out * self.level).astype(np.int16)

    def feed(self, pcm):
        d, p = self.demod.process(pcm.astype(float))
        got = bytes(self.uart.feed((d < 0).astype(np.uint8), True))
        self.screen += got
        return got
