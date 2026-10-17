"""Minimal Minitel (videotex) helpers: encoding, cursor, keys."""
import unicodedata

ESC, SEP, SS2, US = 0x1B, 0x13, 0x19, 0x1F
CLEAR, HOME, CR, LF, BS = 0x0C, 0x1E, 0x0D, 0x0A, 0x08
CURSOR_ON, CURSOR_OFF = b"\x11", b"\x14"

# SEP + code = function keys
KEYS = {0x41: "ENVOI", 0x42: "RETOUR", 0x43: "REPETITION", 0x44: "GUIDE",
        0x45: "ANNULATION", 0x46: "SOMMAIRE", 0x47: "CORRECTION",
        0x48: "SUITE", 0x49: "CONNEXION"}

ACCENTS = {"grave": 0x41, "acute": 0x42, "circumflex": 0x43,
           "diaeresis": 0x48, "cedilla": 0x4B}
_MARKS = {"̀": "grave", "́": "acute", "̂": "circumflex",
          "̈": "diaeresis", "̧": "cedilla"}


def encode(text):
    """str -> Minitel bytes (G0 + G2 accents), '\n' becomes CR LF."""
    out = bytearray()
    for ch in unicodedata.normalize("NFD", text):
        if ch in _MARKS:
            # accent code goes before the base letter (SS2 + accent + letter)
            letter = out.pop()
            out += bytes([SS2, ACCENTS[_MARKS[ch]], letter])
        elif ch == "\n":
            out += bytes([CR, LF])
        elif ch == "£":
            out += bytes([SS2, 0x23])
        elif ch == "œ":
            out += bytes([SS2, 0x7A])
        elif ord(ch) < 0x80:
            out.append(ord(ch))
        else:
            out.append(ord("?"))
    return bytes(out)


def locate(row, col):
    return bytes([US, 0x40 + row, 0x40 + col])


def color(c):            # 0=black .. 7=white (text)
    return bytes([ESC, 0x40 + c])


def background(c):
    return bytes([ESC, 0x50 + c])


DOUBLE_HEIGHT, NORMAL_SIZE = bytes([ESC, 0x4D]), bytes([ESC, 0x4C])
INVERSE, NORMAL_VIDEO = bytes([ESC, 0x5D]), bytes([ESC, 0x5C])
UNDERLINE_ON, UNDERLINE_OFF = bytes([ESC, 0x5A]), bytes([ESC, 0x59])
BLINK, STEADY = bytes([ESC, 0x48]), bytes([ESC, 0x49])


class KeyParser:
    """Turns the raw byte stream into ('char', str) / ('key', NAME) events."""

    def __init__(self):
        self.sep = False
        self.ss2 = False

    def feed(self, data):
        ev = []
        for b in data:
            b &= 0x7F
            if self.sep:
                self.sep = False
                ev.append(("key", KEYS.get(b, "SEP%02X" % b)))
            elif b == SEP:
                self.sep = True
            elif b >= 0x20:
                ev.append(("char", chr(b)))
        return ev
