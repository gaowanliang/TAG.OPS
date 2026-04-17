"""Fast content hashing for image files (xxHash / xxh3_64)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import xxhash
    _HAS_XX = True
except ImportError:   # pragma: no cover
    _HAS_XX = False


def hash_bytes(data: bytes) -> str:
    """Return the xxh3_64 of ``data`` as a 16-char lowercase hex string."""
    if _HAS_XX:
        return xxhash.xxh3_64(data).hexdigest()
    # Fallback: unlikely in production — lets tests / scripts still run.
    import hashlib
    return hashlib.blake2b(data, digest_size=8).hexdigest()


def hash_file(path: str | Path, chunk: int = 1 << 20) -> Optional[str]:
    """Stream-hash a file in 1 MiB chunks to keep memory flat."""
    try:
        if _HAS_XX:
            h = xxhash.xxh3_64()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(chunk), b""):
                    h.update(block)
            return h.hexdigest()
        # Fallback path
        import hashlib
        h = hashlib.blake2b(digest_size=8)
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None
