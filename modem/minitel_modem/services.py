"""The Minitel service itself: a small 3615-style menu."""
import asyncio
import datetime
import os

from . import videotex as vt

DATA = os.environ.get("DATA_DIR", "/data")
TELNET_TARGETS = [t for t in os.environ.get("TELNET_TARGETS", "").split(",") if t]


def title(text):
    return (bytes([vt.CLEAR]) + vt.color(7) + vt.locate(1, 1) + vt.INVERSE
            + vt.encode(f" {text:<38} ") + vt.NORMAL_VIDEO)


async def read_line(s, row, col, width=30, prefix=b""):
    """Line input with local echo; returns text on ENVOI, None on SOMMAIRE."""
    s.send(vt.locate(row, col) + vt.UNDERLINE_ON + vt.CURSOR_ON)
    buf = ""
    while True:
        kind, val = await s.event()
        if kind == "hangup":
            return None
        if kind == "char" and len(buf) < width:
            buf += val
            s.send(vt.encode(val))
        elif kind == "key":
            if val == "ENVOI":
                s.send(vt.UNDERLINE_OFF + vt.CURSOR_OFF)
                return buf
            if val == "CORRECTION" and buf:
                buf = buf[:-1]
                s.send(bytes([vt.BS, 0x20, vt.BS]))
            elif val == "ANNULATION":
                s.send(bytes([vt.BS, 0x20, vt.BS]) * len(buf))
                buf = ""
            elif val in ("SOMMAIRE", "CONNEXION"):
                s.send(vt.UNDERLINE_OFF + vt.CURSOR_OFF)
                return None


async def wait_key(s, names=("SOMMAIRE", "ENVOI", "SUITE")):
    while True:
        kind, val = await s.event()
        if kind == "hangup":
            return None
        if kind == "key" and val in names:
            return val


async def home(s):
    s.send(title("MINITEL - SERVEUR ASTERISK") + vt.locate(4, 1)
           + vt.encode("Bienvenue sur le serveur Minitel !\n\n"
                       " 1 - Date et heure\n"
                       " 2 - Livre d'or\n"
                       " 3 - Test du clavier\n"
                       + (" 4 - Passerelle telnet\n" if TELNET_TARGETS else "")
                       + " 5 - MiniPavi\n"
                       + "\n Votre choix puis ENVOI : "))
    choice = await read_line(s, 13 if TELNET_TARGETS else 12, 25, width=2)
    return choice


async def page_time(s):
    now = datetime.datetime.now()
    s.send(title("DATE ET HEURE") + vt.locate(5, 1) + vt.DOUBLE_HEIGHT
           + vt.encode(now.strftime("%d/%m/%Y\n")) + vt.NORMAL_SIZE
           + vt.encode(now.strftime("\n\n  Il est %H:%M:%S\n"))
           + vt.locate(24, 1) + vt.encode("SOMMAIRE: retour"))
    await wait_key(s)


async def page_guestbook(s):
    path = os.path.join(DATA, "livre_or.txt")
    s.send(title("LIVRE D'OR") + vt.locate(3, 1) + vt.encode("Derniers messages:\n"))
    try:
        lines = open(path, encoding="utf-8").read().splitlines()[-8:]
    except FileNotFoundError:
        lines = []
    for ln in lines:
        s.send(vt.encode(ln[:39] + "\n"))
    s.send(vt.locate(14, 1) + vt.encode("Votre nom : "))
    name = await read_line(s, 14, 13, 20)
    if not name:
        return
    s.send(vt.locate(16, 1) + vt.encode("Message : "))
    msg = await read_line(s, 17, 1, 38)
    if msg:
        os.makedirs(DATA, exist_ok=True)
        stamp = datetime.date.today().strftime("%d/%m")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {name}: {msg}\n")
        s.send(vt.locate(20, 1) + vt.encode("Merci ! Message enregistre."))
        await asyncio.sleep(2)


async def page_keys(s):
    s.send(title("TEST DU CLAVIER") + vt.locate(3, 1)
           + vt.encode("Tapez des touches. SOMMAIRE: retour\n\n"))
    while True:
        kind, val = await s.event()
        if kind == "hangup" or (kind == "key" and val == "SOMMAIRE"):
            return
        s.send(vt.encode(val if kind == "char" else f"[{val}]"))
        if kind == "key":
            s.send(vt.encode("\n"))


async def page_telnet(s):
    s.send(title("PASSERELLE TELNET") + vt.locate(3, 1) + vt.encode("Destinations:\n"))
    for i, t in enumerate(TELNET_TARGETS, 1):
        s.send(vt.encode(f" {i} - {t}\n"))
    s.send(vt.encode("\nNumero : "))
    n = await read_line(s, 5 + len(TELNET_TARGETS) + 2, 10, 2)
    if not n or not n.isdigit() or not 1 <= int(n) <= len(TELNET_TARGETS):
        return
    host, _, port = TELNET_TARGETS[int(n) - 1].partition(":")
    s.send(bytes([vt.CLEAR]) + vt.encode(f"Connexion a {host}...\n"))
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, int(port or 23)), 10)
    except Exception as e:
        s.send(vt.encode(f"Echec: {e}\n"))
        await asyncio.sleep(3)
        return

    async def pump_in():
        while True:
            data = await r.read(256)
            if not data:
                return
            out, i = bytearray(), 0
            while i < len(data):
                b = data[i]
                if b == 0xFF and i + 2 < len(data):      # IAC: refuse options
                    if data[i + 1] in (0xFB, 0xFC):
                        w.write(bytes([0xFF, 0xFE, data[i + 2]]))
                    elif data[i + 1] in (0xFD, 0xFE):
                        w.write(bytes([0xFF, 0xFC, data[i + 2]]))
                    i += 3
                    continue
                if b == 0x1B:                            # drop ANSI sequences
                    j = i + 1
                    if j < len(data) and data[j] == ord("["):
                        j += 1
                        while j < len(data) and not 0x40 <= data[j] <= 0x7E:
                            j += 1
                    i = j + 1
                    continue
                if b in (0x0A, 0x0D, 0x08) or 0x20 <= b < 0x7F:
                    out.append(b)
                i += 1
            s.send(bytes(out).replace(b"\n", b"\r\n").replace(b"\r\r", b"\r"))

    t = asyncio.create_task(pump_in())
    try:
        while not t.done():
            kind, val = await s.event(timeout=0.5)
            if kind == "hangup" or (kind == "key" and val in ("SOMMAIRE", "CONNEXION")):
                break
            if kind == "char":
                w.write(val.encode())
                s.send(b"")        # remote echo expected
            elif kind == "key" and val == "ENVOI":
                w.write(b"\r\n")
    finally:
        t.cancel()
        w.close()


async def page_minipavi(s):
    """Raw TCP relay to MiniPavi (videotex stream both ways, untouched)."""
    host, port = os.environ.get("MINIPAVI_HOST", "go.minipavi.fr"), int(os.environ.get("MINIPAVI_PORT", 516))
    s.send(bytes([vt.CLEAR]) + vt.encode("Connexion a MiniPavi...\n"))
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), 10)
    except Exception as e:
        s.send(vt.encode(f"Echec: {e}\n"))
        await asyncio.sleep(3)
        return
    s.raw = asyncio.Queue()
    await asyncio.sleep(0)

    async def down():
        while True:
            data = await r.read(512)
            if not data:
                return
            s.send(data)
            while s.tx.backlog > 3000 and not s.closed.is_set():
                await asyncio.sleep(0.1)       # 1200 bauds: don't buffer minutes

    async def up():
        while True:
            w.write(await s.raw.get())
            await w.drain()

    tasks = [asyncio.create_task(down()), asyncio.create_task(up())]
    try:
        await asyncio.wait([*tasks, asyncio.create_task(s.closed.wait())],
                           return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        w.close()
        s.raw = None
        while not s.events.empty():
            s.events.get_nowait()


async def menu_app(s):
    pages = {"1": page_time, "2": page_guestbook, "3": page_keys, "4": page_telnet, "5": page_minipavi}
    while not s.closed.is_set():
        choice = await home(s)
        if choice is None:
            if s.closed.is_set():
                return
            continue
        page = pages.get(choice.strip())
        if page and (choice.strip() != "4" or TELNET_TARGETS):
            await page(s)
        elif choice.strip():
            s.send(vt.locate(14, 1) + vt.encode("Choix invalide"))
            await asyncio.sleep(1.5)
