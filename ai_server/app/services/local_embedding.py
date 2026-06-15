from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable


TOKEN_RE = re.compile(r'[\w가-힣]+', re.UNICODE)
LOCAL_HASH_EMBEDDING_MODEL = 'local-hash-v1'
LOCAL_HASH_EMBEDDING_DIMENSIONS = 384


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or '') if token.strip()]


def hash_text_embeddings(
    texts: Iterable[str],
    *,
    dimensions: int = LOCAL_HASH_EMBEDDING_DIMENSIONS,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * dimensions
        tokens = _tokens(text) or ['empty']
        for token in tokens:
            digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], 'little') % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([round(value / norm, 8) for value in vector])
    return vectors
