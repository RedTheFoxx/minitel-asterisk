import asyncio
import logging
import os

from .services import menu_app
from .session import Session


def cfg():
    return {
        "threshold": float(os.environ.get("CARRIER_THRESHOLD", 200000)),
        "tx_level": int(os.environ.get("TX_LEVEL", 8000)),
        "answer_tone_ms": int(os.environ.get("ANSWER_TONE_MS", 800)),
        "record_dir": os.environ.get("RECORD_DIR", ""),
    }


async def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    c = cfg()

    async def handle(r, w):
        await Session(r, w, c).run(menu_app)

    host, port = os.environ.get("LISTEN_HOST", "127.0.0.1"), int(os.environ.get("LISTEN_PORT", 4040))
    srv = await asyncio.start_server(handle, host, port)
    logging.info("AudioSocket modem server on %s:%d", host, port)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
