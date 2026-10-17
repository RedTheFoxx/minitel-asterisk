"""One Minitel call: glue between the AudioSocket stream and the modem DSP."""
import asyncio
import logging
import os
import time
import uuid
import wave

import numpy as np

from . import audiosocket as asock
from .v23 import RxModem, TxModem, FS
from .videotex import KeyParser

log = logging.getLogger("session")
FRAME = 160  # 20 ms


class Session:
    def __init__(self, reader, writer, cfg):
        self.reader, self.writer, self.cfg = reader, writer, cfg
        self.rx = RxModem(threshold=cfg["threshold"])
        self.tx = TxModem(level=cfg["tx_level"])
        self.keys = KeyParser()
        self.events = asyncio.Queue()
        self.closed = asyncio.Event()
        self.call_id = "?"
        self.rec_rx = self.rec_tx = None
        self.raw = None   # optional Queue: unparsed bytes from the Minitel

    # -- app-facing API -------------------------------------------------
    def send(self, data):
        self.tx.write(data)

    async def flush(self):
        """Wait until everything queued has been put on the line."""
        while self.tx.backlog and not self.closed.is_set():
            await asyncio.sleep(0.05)

    async def event(self, timeout=None):
        """Next ('char'|'key'|'hangup', value)."""
        get = self.events.get()
        try:
            return await asyncio.wait_for(get, timeout) if timeout else await get
        except asyncio.TimeoutError:
            return ("timeout", None)

    # -- internals ------------------------------------------------------
    def _record(self):
        d = self.cfg.get("record_dir")
        if not d:
            return
        os.makedirs(d, exist_ok=True)
        base = os.path.join(d, time.strftime("%Y%m%d-%H%M%S-") + self.call_id[:8])
        for name in ("rx", "tx"):
            w = wave.open(f"{base}-{name}.wav", "wb")
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(FS)
            setattr(self, "rec_" + name, w)

    async def _tx_loop(self):
        t = time.monotonic()
        while not self.closed.is_set():
            t += FRAME / FS
            pcm = self.tx.generate(FRAME)
            if self.rec_tx:
                self.rec_tx.writeframes(pcm.tobytes())
            try:
                self.writer.write(asock.audio_packet(pcm.tobytes()))
                await self.writer.drain()
            except (ConnectionError, OSError):
                break
            await asyncio.sleep(max(0, t - time.monotonic()))

    async def run(self, app):
        tx_task = app_task = None
        was_carrier = False
        stat = time.monotonic()
        try:
            while True:
                kind, payload = await asock.read_packet(self.reader)
                if kind == asock.KIND_UUID:
                    self.call_id = str(uuid.UUID(bytes=payload))
                    log.info("call %s: answered", self.call_id)
                    self._record()
                    self.tx.start(tone_ms=self.cfg["answer_tone_ms"])
                    tx_task = asyncio.create_task(self._tx_loop())
                    app_task = asyncio.create_task(self._app(app))
                elif kind == asock.KIND_AUDIO:
                    if self.rec_rx:
                        self.rec_rx.writeframes(payload)
                    pcm = np.frombuffer(payload, dtype="<i2")
                    data = self.rx.feed(pcm)
                    if self.rx.carrier != was_carrier:
                        was_carrier = self.rx.carrier
                        log.info("call %s: Minitel carrier %s", self.call_id,
                                 "UP" if was_carrier else "LOST")
                        if not was_carrier:
                            self.events.put_nowait(("hangup", None))
                    if data and self.raw is not None:
                        self.raw.put_nowait(data)
                    if data:
                        log.debug("rx %r", data)
                        for ev in self.keys.feed(data):
                            self.events.put_nowait(ev)
                    if time.monotonic() - stat > 5:
                        stat = time.monotonic()
                        log.info("call %s: rx level=%.0f carrier=%s uart_err=%d",
                                 self.call_id, self.rx.level, self.rx.carrier,
                                 self.rx.uart.errors)
                elif kind in (asock.KIND_HANGUP, asock.KIND_ERROR):
                    break
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.closed.set()
            self.events.put_nowait(("hangup", None))
            for t in (app_task, tx_task):
                if t:
                    t.cancel()
            for w in (self.rec_rx, self.rec_tx):
                if w:
                    w.close()
            self.writer.close()
            log.info("call %s: ended", self.call_id)

    async def _app(self, app):
        try:
            # wait for the Minitel to bring its 390 Hz carrier up
            for _ in range(600):
                if self.rx.carrier or self.closed.is_set():
                    break
                await asyncio.sleep(0.1)
            else:
                log.info("call %s: no Minitel carrier, hanging up", self.call_id)
                self.writer.close()
                return
            await asyncio.sleep(0.5)
            await app(self)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("app crashed")
        finally:
            await self.flush()
            self.writer.close()
