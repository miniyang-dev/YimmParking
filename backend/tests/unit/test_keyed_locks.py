from __future__ import annotations

import threading

from yimmparking.application.keyed_locks import KeyedLocks


def test_an_entry_is_dropped_once_nobody_holds_it() -> None:
    locks = KeyedLocks()
    with locks.hold("a"):
        assert len(locks) == 1
    assert len(locks) == 0


def test_an_entry_is_dropped_even_when_the_work_raises() -> None:
    locks = KeyedLocks()
    try:
        with locks.hold("a"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert len(locks) == 0


def test_the_same_key_waits_and_another_key_does_not() -> None:
    locks = KeyedLocks()
    inside = threading.Event()
    release = threading.Event()
    same_entered = threading.Event()
    other_entered = threading.Event()

    def hold(key: str, entered: threading.Event) -> None:
        with locks.hold(key):
            entered.set()
            if key == "a" and entered is inside:
                release.wait(5)

    first = threading.Thread(target=hold, args=("a", inside))
    first.start()
    assert inside.wait(5)

    same = threading.Thread(target=hold, args=("a", same_entered))
    other = threading.Thread(target=hold, args=("b", other_entered))
    same.start()
    other.start()

    assert other_entered.wait(5)  # another key runs while "a" is held
    assert not same_entered.wait(0.2)  # the same key waits for the first holder
    release.set()
    for t in (first, same, other):
        t.join(5)
    assert same_entered.is_set()
    assert len(locks) == 0
