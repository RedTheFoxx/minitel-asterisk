"""Offline DSP test: server modem <-> simulated Minitel, through A-law + noise."""
import audioop
import sys

import numpy as np

from minitel_modem.v23 import RxModem, TxModem
from tests.sim import MinitelSim

rng = np.random.default_rng(1)


def line(pcm, snr_noise):
    pcm = pcm.astype(np.int16)
    a = audioop.lin2alaw(pcm.tobytes(), 2)
    pcm = np.frombuffer(audioop.alaw2lin(a, 2), dtype="<i2").astype(float)
    pcm += rng.normal(0, snr_noise, len(pcm))
    return np.clip(pcm, -32768, 32767).astype(np.int16)


def run(noise, message_up, message_down, seconds=22):
    tx, rx, mt = TxModem(level=8000), RxModem(threshold=400), MinitelSim(level=3000)
    tx.start(tone_ms=800)
    mt.on = True
    mt.type(message_up)
    got_up = bytearray()
    carrier_seen = False
    for i in range(seconds * 50):
        if i == 70:
            tx.write(message_down)   # after answer tone + idle mark
        down = tx.generate(160)           # server -> minitel
        up = mt.generate(160)             # minitel -> server
        mt.feed(line(down, noise))
        got_up += rx.feed(line(up, noise))
        carrier_seen |= rx.carrier
    return bytes(got_up), bytes(mt.screen), carrier_seen, rx.uart.errors, mt.uart.errors


ok = True
up = bytes(range(0x20, 0x7F)) + b"\x13\x41" + b"HELLO MINITEL\r"
down = bytes([0x0C, 0x1F, 0x41, 0x41]) + b"Bienvenue sur le serveur Minitel 1200 bauds\r\n" * 3
for noise in (0, 30, 100):
    gu, gd, car, e1, e2 = run(noise, up, down)
    # allow the trailing chars of the tone preamble: compare as suffix/prefix match
    r_up = gu == up
    r_dn = gd.endswith(down) or down in gd
    print(f"noise={noise:4d}  up(75bd) {'OK' if r_up else 'FAIL'} ({len(gu)}/{len(up)})  "
          f"down(1200bd) {'OK' if r_dn else 'FAIL'} ({len(gd)}/{len(down)})  "
          f"carrier={car} err={e1}/{e2}")
    ok &= r_up and r_dn
sys.exit(0 if ok else 1)
