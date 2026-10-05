from __future__ import annotations

import hashlib
import hmac
import time


def mint_token(secret: str, pin: str) -> str:
    """Stateless bearer token. Binding the PIN in means changing the PIN revokes every token."""
    return hmac.new(secret.encode(), b"transform-token-v2:" + pin.encode(), hashlib.sha256).hexdigest()


def verify_token(secret: str, pin: str, token: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(mint_token(secret, pin), token)


def verify_pin(expected: str, given: str) -> bool:
    return hmac.compare_digest(expected.encode(), given.encode())


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_sec: int = 900):
        self.max_attempts, self.window = max_attempts, window_sec
        self._fails: dict[str, list[float]] = {}

    def _prune(self, key: str) -> list[float]:
        now = time.monotonic()
        lst = [t for t in self._fails.get(key, []) if now - t < self.window]
        self._fails[key] = lst
        return lst

    def allow(self, key: str) -> bool:
        return len(self._prune(key)) < self.max_attempts

    def record_failure(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
