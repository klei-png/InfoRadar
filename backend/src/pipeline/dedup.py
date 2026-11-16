import hashlib
import re
from sys import path

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

#tracking parameters that need to be filtered
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "ref", "from", "spm", "fbclid"
}

SIMHASH_THRESHOLD = 3

def normalize_url(url: str) -> str:
    try:
        s = urlsplit(url.strip())
    except Exception:
        return url

    host = (s.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    q = [(k,v) for k,v in parse_qsl(s.query) if k not in TRACKING_PARAMS]
    q.sort()

    path = s.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(q), ""))

def url_hash(url: str) -> str:
    return hashlib.md5(normalize_url(url).encode("utf-8")).hexdigest()

#L2 deduplication: title simhash fingerprint
_CLEAN_RE = re.compile(r"[\W_]+",re.UNICODE)

def _tokenize(text: str) -> list[str]:
    t = _CLEAN_RE.sub(" ",text.lower())
    out = []
    for seg in t.split():
        if any("\u4e00" <= ch <= "\u9fff" for ch in seg):
            out += [seg[i:i+2] for i in range(len(seg)-1)] or [seg]
        else:
            out.append(seg)
    return out


def simhash64(text: str) -> int:
    v = [0] * 64
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1

    out = 0
    for i in range(64):
        if v[i] > 0:
            out |= (1 << i)
    return out

def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()

def _exists_by_url_hash(url_hash_value: str) -> bool:
    try:

        return exists_by_url_hash(url_hash_value)
    except (ImportError, AttributeError):
        pass
    try:
        from src.db.repository import get_item_by_url_hash
        return get_item_by_url_hash(url_hash_value) is not None
    except (ImportError, AttributeError):
        return False