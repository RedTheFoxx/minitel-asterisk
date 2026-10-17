"""ITU-T V.23 (mode 2) soft-modem, server side, for 8 kHz audio.

The Minitel is the calling terminal:
  server -> Minitel : 1200 baud FSK, mark(1)=1300 Hz, space(0)=2100 Hz
  Minitel -> server :   75 baud FSK, mark(1)= 390 Hz, space(0)= 450 Hz
Characters are 7E1 framed (start, 7 data bits LSB first, even parity, stop).
"""
import math
from collections import deque

import numpy as np

FS = 8000


def fir_lowpass(cutoff, ntaps, fs=FS):
    n = np.arange(ntaps) - (ntaps - 1) / 2
    h = np.sinc(2 * cutoff / fs * n) * (2 * cutoff / fs) * np.hamming(ntaps)
    return h / h.sum()


def frame_7e1(byte):
    """Bits (first transmitted first) of one 7E1 character."""
    d = [(byte >> i) & 1 for i in range(7)]
    return [0] + d + [sum(d) & 1, 1]


class FskDemod:
    """Streaming FSK discriminator.

    Mixes to baseband around `center`, low-passes, and returns the smoothed
    instantaneous frequency deviation (rad/sample, >0 = above center) and the
    baseband power, one value per input sample.
    """

    def __init__(self, center, cutoff, ntaps, smooth, fs=FS):
        self.w = 2 * math.pi * center / fs
        self.h = fir_lowpass(cutoff, ntaps, fs)
        self.n0 = 0
        self.tail = np.zeros(ntaps - 1, complex)
        self.prev = 0j
        self.k = smooth
        self.dtail = np.zeros(smooth - 1)
        self.ptail = np.zeros(smooth - 1)

    def process(self, x):
        x = np.asarray(x, float)
        ph = (self.n0 + np.arange(len(x))) * self.w
        self.n0 += len(x)
        m = x * np.exp(-1j * ph)
        buf = np.concatenate([self.tail, m])
        z = np.convolve(buf, self.h, "valid")
        self.tail = buf[len(buf) - (len(self.h) - 1):]
        zz = np.concatenate([[self.prev], z])
        self.prev = z[-1]
        d = np.angle(zz[1:] * np.conj(zz[:-1]))
        # An unlocked prev (0j) yields angle 0: harmless.
        p = np.abs(z) ** 2
        ones = np.ones(self.k) / self.k
        db = np.concatenate([self.dtail, d])
        pb = np.concatenate([self.ptail, p])
        self.dtail = db[len(db) - (self.k - 1):] if self.k > 1 else db[:0]
        self.ptail = pb[len(pb) - (self.k - 1):] if self.k > 1 else pb[:0]
        return np.convolve(db, ones, "valid"), np.convolve(pb, ones, "valid")


class Uart7E1:
    """Asynchronous receiver working on a per-sample bit stream."""

    def __init__(self, baud, fs=FS):
        self.spb = fs / baud
        self.pos = 0          # absolute sample index of the next sample
        self.sched = None     # list of sampling instants for the current char
        self.idx = 0
        self.bits = []
        self.errors = 0

    def reset(self):
        self.sched = None

    def feed(self, bitstream, active):
        out = []
        for b in bitstream:
            pos = self.pos
            self.pos += 1
            if self.sched is None:
                if active and b == 0:
                    s = pos
                    self.sched = [s + self.spb * (0.5 + k) for k in range(10)]
                    self.idx = 0
                    self.bits = []
                continue
            if pos + 1 > self.sched[self.idx]:
                # this sample is the one closest to the sampling instant
                self.bits.append(b)
                self.idx += 1
                if self.idx == 1 and b != 0:       # false start
                    self.sched = None
                    continue
                if self.idx == 10:
                    d = self.bits[1:8]
                    val = sum(bit << i for i, bit in enumerate(d))
                    if (sum(d) + self.bits[8]) & 1 or self.bits[9] != 1:
                        self.errors += 1
                    out.append(val)
                    self.sched = None
                    # resume edge detection right at the stop bit
        return out


class RxModem:
    """Minitel -> server channel (75 baud) with carrier detection."""

    def __init__(self, threshold=400.0, loss_s=1.5, baud=75, center=420, fs=FS):
        self.demod = FskDemod(center, cutoff=95, ntaps=121,
                              smooth=int(fs / baud / 4), fs=fs)
        self.uart = Uart7E1(baud, fs)
        self.thr = threshold
        self.loss_samples = int(loss_s * fs)
        self.quiet = self.loss_samples
        self.carrier = False
        self.level = 0.0
        self.fs = fs

    def feed(self, pcm):
        """pcm: int16 ndarray. Returns bytes received (carrier status in .carrier)."""
        d, p = self.demod.process(pcm.astype(float))
        self.level = float(np.mean(p))
        up = p > self.thr
        # carrier state machine at sample granularity (cheap: chunk level)
        if up.mean() > 0.5:
            self.quiet = 0
            if not self.carrier:
                self.carrier = True
                self.uart.reset()
        else:
            self.quiet += len(pcm)
            if self.carrier and self.quiet >= self.loss_samples:
                self.carrier = False
        bits = (d < 0).astype(np.uint8)       # below center = mark = 1
        got = self.uart.feed(bits, self.carrier)
        return bytes(got)


class TxModem:
    """Server -> Minitel channel (1200 baud, phase-continuous FSK)."""

    def __init__(self, level=8000, baud=1200, f_mark=1300, f_space=2100, fs=FS):
        self.level = level
        self.spb = fs / baud
        self.fm, self.fs_, self.fsamp = f_mark, f_space, fs
        self.phase = 0.0
        self.bits = deque()
        self.rem = 0.0
        self.cur = 1
        self.on = False          # carrier on?
        self.tone = None         # (freq, samples_left) preamble
        self.drain = deque()

    def start(self, tone_hz=2100, tone_ms=800):
        self.tone = [tone_hz, int(tone_ms * self.fsamp / 1000)]
        self.on = True

    def stop(self):
        self.on = False
        self.tone = None

    def write(self, data):
        for byte in data:
            self.bits.extend(frame_7e1(byte & 0x7F))

    @property
    def backlog(self):
        return len(self.bits)

    def generate(self, n):
        out = np.zeros(n, dtype=np.int16)
        if not self.on:
            self.bits.clear()
            return out
        two_pi = 2 * math.pi / self.fsamp
        ph = self.phase
        buf = np.empty(n)
        for i in range(n):
            if self.tone and self.tone[1] > 0:
                f = self.tone[0]
                self.tone[1] -= 1
            else:
                if self.tone:
                    self.tone = None
                    self.rem = 0.0
                if self.rem <= 0:
                    self.cur = self.bits.popleft() if self.bits else 1
                    self.rem += self.spb
                self.rem -= 1
                f = self.fm if self.cur else self.fs_
            ph += two_pi * f
            buf[i] = math.sin(ph)
        self.phase = ph % (2 * math.pi)
        return (buf * self.level).astype(np.int16)
