"""Fake Minitel on the other side of Asterisk (end-to-end test).

Run it, then:  asterisk -rx "channel originate AudioSocket/127.0.0.1:4041/<uuid> extension s@minitel-server"
"""
import asyncio
import struct
import sys
import time

import numpy as np

from minitel_modem import audiosocket as asock
from tests.sim import MinitelSim

SCRIPT = [(4.0, b"1\x13\x41"), (9.0, b"\x13\x46"), (11.0, b"2\x13\x41")]


async def handle(r, w):
    m, t0, i, n = MinitelSim(3000), time.monotonic(), 0, 0
    try:
        while True:
            kind, payload = await asock.read_packet(r)
            if kind == asock.KIND_AUDIO:
                el = time.monotonic() - t0
                if el > 1.5:
                    m.on = True
                if i < len(SCRIPT) and el > SCRIPT[i][0]:
                    m.type(SCRIPT[i][1]); i += 1
                m.feed(np.frombuffer(payload, "<i2"))
                w.write(asock.audio_packet(m.generate(len(payload) // 2).tobytes()))
                await w.drain()
                n += 1
                if el > 16:
                    break
            elif kind in (asock.KIND_HANGUP, asock.KIND_ERROR):
                break
    except asyncio.IncompleteReadError:
        pass
    printable = bytes(b if 32 <= b < 127 else 46 for b in m.screen)
    print("Minitel screen bytes:", len(m.screen), "uart errors:", m.uart.errors)
    print(printable.decode())
    w.close()


async def main():
    srv = await asyncio.start_server(handle, "127.0.0.1", 4041)
    print("sim minitel waiting on 4041", flush=True)
    async with srv:
        await srv.serve_forever()

asyncio.run(main())
