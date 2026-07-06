"""Content hashing for the cache key."""
import hashlib


def compute_content_hash(subject: str, body: str) -> str:
    """sha256 of normalized subject+body. Identical tickets -> identical hash."""
    normalized = f"{subject.strip().lower()}\n{body.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
