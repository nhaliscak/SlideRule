"""A wall-clock limit for long calculations, usable from any thread and inside the in-browser (Pyodide) engine.

``with time_limit(seconds):`` abandons the enclosed work with :class:`TimeLimitExceeded` once the deadline has passed. Limits nest
(the earliest deadline wins) and ``time_limit(None)`` adds none, which is how "no limit" is expressed.

Two mechanisms, chosen automatically:

* **Watchdog timer** (installed Python, any thread): a daemon timer raises an exception *inside the calculating thread* when the
  deadline passes (``PyThreadState_SetAsyncExc``). It costs nothing while the work runs, which matters because SymPy makes millions of calls.
* **Profile hook** (where threads cannot be started, e.g. Pyodide): ``sys.setprofile`` checks the clock every few hundred calls.

Both act between Python bytecodes/calls, so one long native operation (a single enormous integer power, say) can overrun the limit;
SymPy is pure Python, so ordinary symbolic work is interrupted promptly. Nothing is killed: the work is abandoned by an exception, which is
a ``BaseException`` so that SymPy's own ``except Exception`` blocks cannot swallow it.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from contextlib import contextmanager


class TimeLimitExceeded(Exception):
    def __init__(self, seconds: float):
        super().__init__(f"the calculation took longer than {seconds:g} s and was stopped")
        self.seconds = seconds


class _Stop(BaseException):
    pass


_local = threading.local()
_watchdog_ok = True            # becomes False the first time a thread cannot be started


def _raise_in(thread_id: int) -> None:
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), ctypes.py_object(_Stop))


def _cancel_pending(thread_id: int) -> None:
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), None)


def _make_hook(stack: list):
    calls = 0

    def hook(frame, event, arg):
        nonlocal calls
        calls += 1
        if calls & 255:
            return
        if stack and time.monotonic() > min(d for d, _ in stack):
            raise _Stop
    return hook


@contextmanager
def time_limit(seconds: float | None):
    """Stop the enclosed work with :class:`TimeLimitExceeded` after ``seconds`` (``None``: no new limit)."""
    global _watchdog_ok
    if seconds is None:
        yield
        return
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = _local.stack = []
    entry = (time.monotonic() + seconds, seconds)
    outermost = not stack
    tid = threading.get_ident()
    fired = threading.Event()
    timer = None
    previous_profile = None
    hooked = False
    if _watchdog_ok:
        def fire():
            fired.set()
            _raise_in(tid)
        timer = threading.Timer(seconds, fire)
        timer.daemon = True
        try:
            timer.start()
        except RuntimeError:           # no threads here (Pyodide): fall back to the profile hook for good
            _watchdog_ok = False
            timer = None
    if timer is None and outermost:
        previous_profile = sys.getprofile()
        sys.setprofile(_make_hook(stack))
        hooked = True
    stack.append(entry)
    try:
        try:
            yield
        finally:
            stack.remove(entry)
            if timer is not None:
                timer.cancel()
                if fired.is_set():           # fired just as the block ended: make sure no stray exception arrives later
                    try:
                        _cancel_pending(tid)
                    except Exception:        # noqa: BLE001
                        pass
            if hooked:
                sys.setprofile(previous_profile)
    except _Stop:
        if time.monotonic() > entry[0]:
            raise TimeLimitExceeded(seconds) from None
        raise            # an enclosing limit expired, not this one
