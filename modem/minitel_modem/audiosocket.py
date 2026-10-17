"""Asterisk AudioSocket protocol (TCP): 1 byte type, 2 bytes big-endian length."""
import asyncio
import struct

KIND_HANGUP, KIND_UUID, KIND_DTMF, KIND_AUDIO, KIND_ERROR = 0x00, 0x01, 0x03, 0x10, 0xFF


async def read_packet(reader):
    hdr = await reader.readexactly(3)
    kind, length = hdr[0], struct.unpack(">H", hdr[1:])[0]
    payload = await reader.readexactly(length) if length else b""
    return kind, payload


def audio_packet(pcm_bytes):
    return struct.pack(">BH", KIND_AUDIO, len(pcm_bytes)) + pcm_bytes
