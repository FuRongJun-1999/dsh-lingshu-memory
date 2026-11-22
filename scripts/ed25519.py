"""Minimal Ed25519 (RFC 8032) sign/verify using only the standard library.

Scope note: this is a compact reference implementation for the stage gate's
attestation check and its self-tests. It is not constant-time and must not be
used to protect long-lived secrets; it verifies externally produced signatures."""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)


def _xrecover(y):
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * I) % P
    if (x * x - xx) % P != 0:
        return None
    return x


BY = 4 * pow(5, P - 2, P) % P
BX = _xrecover(BY)
if BX % 2 != 0:
    BX = P - BX
BASE = (BX % P, BY % P)


def _encode_point(point):
    x, y = point
    data = bytearray(y.to_bytes(32, 'little'))
    data[31] |= (x & 1) << 7
    return bytes(data)


def _decode_point(data):
    if len(data) != 32:
        return None
    value = bytearray(data)
    sign = value[31] >> 7
    value[31] &= 0x7F
    y = int.from_bytes(bytes(value), 'little')
    if y >= P:
        return None
    x = _xrecover(y)
    if x is None:
        return None
    if (x & 1) != sign:
        x = (P - x) % P
    return (x, y)


def _add(first, second):
    x1, y1 = first
    x2, y2 = second
    denominator = D * x1 * x2 * y1 * y2 % P
    x3 = (x1 * y2 + x2 * y1) * pow(1 + denominator, P - 2, P)
    y3 = (y1 * y2 + x1 * x2) * pow(1 - denominator, P - 2, P)
    return (x3 % P, y3 % P)


def _multiply(point, scalar):
    result = (0, 1)
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        scalar >>= 1
    return result


def _clamp(seed):
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], 'little')
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def public_key(seed):
    if len(seed) != 32:
        raise ValueError('seed must be 32 bytes')
    scalar, _prefix = _clamp(seed)
    return _encode_point(_multiply(BASE, scalar))


def sign(seed, message):
    if len(seed) != 32:
        raise ValueError('seed must be 32 bytes')
    scalar, prefix = _clamp(seed)
    public = _encode_point(_multiply(BASE, scalar))
    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), 'little') % L
    r_point = _encode_point(_multiply(BASE, nonce))
    challenge = int.from_bytes(hashlib.sha512(r_point + public + message).digest(), 'little') % L
    s = (nonce + challenge * scalar) % L
    return r_point + s.to_bytes(32, 'little')


def verify(public, message, signature):
    if len(public) != 32 or len(signature) != 64:
        return False
    point = _decode_point(public)
    if point is None:
        return False
    r_point = _decode_point(signature[:32])
    if r_point is None:
        return False
    s = int.from_bytes(signature[32:], 'little')
    if s >= L:
        return False
    if _multiply(point, 8) == (0, 1) or _multiply(r_point, 8) == (0, 1):
        return False
    challenge = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), 'little') % L
    left = _multiply(BASE, s)
    right = _add(r_point, _multiply(point, challenge))
    return left == right