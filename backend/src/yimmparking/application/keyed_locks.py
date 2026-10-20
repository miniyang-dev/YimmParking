"""One lock per key, so identical work waits for the first caller while unrelated work runs.

The caches in front of billed providers use this: two identical requests at once must not both be
billed, but a request for another place must not queue behind a slow provider call. An entry is
dropped as soon as nobody holds or waits on it, so the table does not grow with every key seen.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class KeyedLocks:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, tuple[threading.Lock, int]] = {}  # key -> (lock, holders + waiters)

    @contextmanager
    def hold(self, key: str) -> Iterator[None]:
        with self._guard:
            lock, users = self._locks.get(key, (threading.Lock(), 0))
            self._locks[key] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self._guard:
                lock, users = self._locks[key]
                if users == 1:
                    del self._locks[key]
                else:
                    self._locks[key] = (lock, users - 1)

    def __len__(self) -> int:
        with self._guard:
            return len(self._locks)
