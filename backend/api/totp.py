import base64
import hashlib
import hmac
import struct
import time


def new_secret():
    import secrets
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret):
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_for(secret, counter):
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return f"{value % 1_000_000:06d}"


def verify(secret, code, window=1):
    if not secret or not isinstance(code, str) or not code.isdigit() or len(code) != 6:
        return False
    counter = int(time.time()) // 30
    return any(hmac.compare_digest(code_for(secret, counter + step), code) for step in range(-window, window + 1))


def otpauth_uri(secret, username, issuer="Marian"):
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
