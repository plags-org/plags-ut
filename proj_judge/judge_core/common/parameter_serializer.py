import base64

ALTCHARS: bytes = b"_+"


def encode_parameter(raw: str) -> str:
    return str(base64.b64encode(bytes(raw, "utf_8"), ALTCHARS), encoding="ascii")


def decode_parameter(encoded: str) -> str:
    return str(base64.b64decode(bytes(encoded, "ascii"), ALTCHARS), encoding="utf_8")
