"""
Pyjo.Reactor.Uvloop - Low-level event reactor on uvloop
=======================================================
::

    from Pyjo.Reactor.Uvloop import Uvloop

    # Watch if handle becomes readable or writable
    reactor = Uvloop()
    reactor.io(first, lambda reactor, writable: print(
        'First handle is writable' if writable else 'First handle is readable'
    ))

    # Or import the module, as in Google Python Style Guide

    import Pyjo.Reactor.Uvloop

    # Watch if handle becomes readable or writable
    reactor = Pyjo.Reactor.Uvloop.new()
    reactor.io(first, lambda reactor, writable: print(
        'First handle is writable' if writable else 'First handle is readable'
    ))

    # Change to watching only if handle becomes writable
    reactor.watch(first, False, True)

    # Watch a file descriptor if it becomes readable
    reactor.io(fd, lambda reactor, writable: print(
        'Second handle is writable' if writable else 'Second handle is readable'
    )).watch(fd, True, False)

    # Add a timer
    def timeout(reactor):
        reactor.remove(first)
        reactor.remove(fd)
        print('Timeout!')

    reactor.timer(15, timeout)

    # Start reactor if necessary
    if not reactor.is_running:
        reactor.start()

:mod:`Pyjo.Reactor.Uvloop` is a low-level event reactor based on
`uvloop <https://uvloop.readthedocs.io>`_, the implementation of the event
loop of :mod:`asyncio` on libuv. It is :mod:`Pyjo.Reactor.Asyncio` with an
event loop of its own of uvloop, in the place of the one of :mod:`asyncio`,
so that the servers of Pyjoyment, as :mod:`Pyjo.Server.Daemon`,
:mod:`Pyjo.Server.Prefork` and :mod:`Pyjo.Server.Prethread`, and the blocking
requests of its user agent run on uvloop. ``PYJO_REACTOR`` selects it for
:mod:`Pyjo.IOLoop`::

    PYJO_REACTOR=Pyjo.Reactor.Uvloop python myapp.py daemon

The loop of uvloop is a loop of :mod:`asyncio`, so coroutines, tasks and the
libraries of :mod:`asyncio` run along with the reactor, as with
:mod:`Pyjo.Reactor.Asyncio`. A reactor uses the event loop it is given, or
else the loop that is running, as inside :func:`asyncio.run`, of
:mod:`asyncio` or of uvloop, and only a loop of its own is one of uvloop. An
ASGI server on uvloop, as uvicorn and Hypercorn, runs the loop itself, which
:mod:`Pyjo.Reactor.Asyncio` takes already, so it needs no reactor of uvloop.
In the child of a fork, as a worker of :mod:`Pyjo.Server.Prefork`, the
reactor moves to a new loop of its own of uvloop. The wakeup fd of the
signals that a program sets with :func:`signal.set_wakeup_fd`, as the workers
of :mod:`Pyjo.Server.Prefork` do, is written to on a signal while a loop of
its own runs, as with the loop of :mod:`asyncio`, although uvloop sets one of
its own. A timer of a loop of its own, as :func:`asyncio.sleep`, is never due
before its time, as with the loop of :mod:`asyncio`, although libuv counts it
in whole milliseconds, so it may be up to two milliseconds late.

uvloop runs on Linux and macOS, not on Windows, and on CPython, not on PyPy.
The ``PYJO_ASYNCIO_SLOW_CALLBACK`` environment variable sets the
``slow_callback_duration`` of a loop of its own in seconds, as for
:mod:`Pyjo.Reactor.Asyncio`.

Events
------

:mod:`Pyjo.Reactor.Uvloop` inherits all events from :mod:`Pyjo.Reactor.Asyncio`.

See also
--------

:mod:`Pyjo.Reactor.Asyncio`, :mod:`Pyjoyment`, https://github.com/pyjoyment/Pyjoyment.

Classes
-------
"""

import Pyjo.Reactor.Asyncio

import asyncio
import importlib.metadata
import math
import os
import select
import signal
import socket
import sys
import threading
import weakref

from collections.abc import Callable
from typing import Any

import uvloop


__version__ = importlib.metadata.version('Pyjo-Reactor-Uvloop')
"""The version of the distribution, of its metadata, which the workflow Automated version sets in pyproject.toml."""


class Pyjo_Reactor_Uvloop(Pyjo.Reactor.Asyncio.object):
    """
    :mod:`Pyjo.Reactor.Uvloop` inherits all methods from
    :mod:`Pyjo.Reactor.Asyncio`.
    """

    # A loop of its own of uvloop, in the place of the one of asyncio; the rest is what Pyjo.Reactor.Asyncio does with a
    # loop of its own, which is closed with the reactor, and at the exit of the interpreter after its tasks
    def _own_loop(self) -> asyncio.AbstractEventLoop:
        loop = self._own = _new_event_loop()
        Pyjo.Reactor.Asyncio._OWN.add(loop)  # pyright: ignore[reportPrivateUsage]
        self._finalizer = weakref.finalize(self, Pyjo.Reactor.Asyncio._close, loop)  # pyright: ignore[reportPrivateUsage]
        Pyjo.Reactor.Asyncio._register()  # pyright: ignore[reportPrivateUsage]
        return loop


class _Loop(uvloop.Loop):  # pyright: ignore[reportUntypedBaseClass]
    _halt: asyncio.Handle | None = None
    _halted = False
    _relay: tuple[socket.socket, socket.socket] | None = None

    # After stop, uvloop ends the iteration of libuv, and the iteration that a callback of I/O stops goes on to the poll of
    # the next one, which calls the readers and the writers that are ready again, where the loop of asyncio ends with the
    # callbacks of its select, so that an event of the reactor that stops it, or ends one_tick, would be followed by the
    # same events again. A callback that stop schedules runs before that poll, as uvloop runs the ready callbacks before
    # it, and halts the readers and the writers until the end of the run; the handles are ready in the next run still. A
    # stop in a ready callback, as a timer of no time of the reactor, does not halt the poll of its own iteration, as the
    # loop of asyncio runs the callbacks of its select along with it, which would starve the I/O otherwise
    def run_forever(self) -> None:
        self._halted = False
        try:
            return self._relayed()
        finally:
            self._halted = False
            if (halt := self._halt) is not None:
                self._halt = None
                halt.cancel()

    def stop(self) -> None:
        if self._halt is None and self.is_running():
            self._halt = self.call_soon(self._halting)
        super().stop()

    def _halting(self) -> None:
        self._halt = None
        self._halted = True

    # libuv counts a timer in whole milliseconds from its clock, which it rounds down, and uvloop rounds the delay, so
    # that a timer, as asyncio.sleep, is due up to a millisecond before its time by time.monotonic, where the loop of
    # asyncio is never early; the delay is rounded up, with the millisecond that the clock loses (MagicStack/uvloop#755).
    # call_at of uvloop calls it too
    def call_later(
        self, delay: float, callback: Callable[..., Any], *args: Any, context: Any = None
    ) -> asyncio.TimerHandle:
        if 0 < delay < math.inf:
            delay = (math.ceil(delay * 1000) + 1) / 1000
        return super().call_later(delay, callback, *args, context=context)

    def __init__(self) -> None:
        super().__init__()
        self._rearm: set[int] = set()
        self._errors: select.poll | None = select.poll() if sys.platform == 'linux' else None
        self._watchers: dict[int, list[tuple[Any, Callable[..., Any], tuple[Any, ...]] | None]] = {}

    def add_reader(self, fd: Any, callback: Callable[..., Any], *args: Any) -> None:
        self._watch(fd, 0, callback, args)

    def add_writer(self, fd: Any, callback: Callable[..., Any], *args: Any) -> None:
        self._watch(fd, 1, callback, args)

    def remove_reader(self, fd: Any) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._unwatch(fd, 0)
        return bool(super().remove_reader(fd))

    def remove_writer(self, fd: Any) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._unwatch(fd, 1)
        return bool(super().remove_writer(fd))

    # libuv sets a handle that it watches to the non-blocking mode, and never back, where the loop of asyncio leaves it;
    # the mode belongs to the open file description that other processes share, as the terminal of the standard input
    # and output of Pyjo.IOLoop.Stdio, which reads and writes it in the blocking mode and is left non-blocking for the
    # shell after it, so a handle that was blocking is set back, as libuv only waits for it and does not read it
    def _watch(self, fd: Any, writable: int, callback: Callable[..., Any], args: tuple[Any, ...]) -> None:
        fileno = _fileno(fd)
        blocking = _blocking(fileno)
        add = super().add_writer if writable else super().add_reader
        add(fd, self._ready, fileno, callback, *args)
        if blocking:
            os.set_blocking(fileno, True)
        self._watchers.setdefault(fileno, [None, None])[writable] = (fd, callback, args)

    def _unwatch(self, fd: Any, writable: int) -> None:
        fileno = _fileno(fd)
        if (watcher := self._watchers.get(fileno)) is not None:
            watcher[writable] = None
            if watcher == [None, None]:
                del self._watchers[fileno]

    # On an error of a handle, as a pipe whose reader has closed it or a socket that the peer has reset, libuv of Linux
    # stops watching it and calls its reader and its writer once, and uvloop closes its watcher but keeps it, so that the
    # handle is not watched anymore, also by the next add_reader or add_writer, where the loop of asyncio calls them for
    # as long as the error lasts; a handle with an error is watched again, so that a callback that writes nothing at that
    # time, or that the halt after stop leaves out, sees it next time
    def _ready(self, fileno: int, callback: Callable[..., Any], *args: Any) -> None:
        try:
            if not self._halted:
                callback(*args)
        finally:
            if fileno in self._watchers and fileno not in self._rearm and self._error(fileno):
                self._rearm.add(fileno)
                self.call_soon(self._rearming, fileno)

    # Only libuv of Linux stops watching a handle on its error, which kqueue of macOS does not report so
    def _error(self, fileno: int) -> bool:
        if (poll := self._errors) is None:
            return False
        poll.register(fileno, 0)
        try:
            return any(events & select.POLLERR for _, events in poll.poll(0))
        except OSError:
            return False
        finally:
            poll.unregister(fileno)

    def _rearming(self, fileno: int) -> None:
        self._rearm.discard(fileno)
        if (watcher := self._watchers.get(fileno)) is None:
            return
        super().remove_reader(fileno)
        super().remove_writer(fileno)
        for writable, watched in enumerate(list(watcher)):
            if watched is not None:
                self._watch(watched[0], writable, watched[1], watched[2])

    # uvloop sets the wakeup fd of the signals to a socket of its own while it runs, in the main thread, so that the one
    # that the program has set, as a worker of Pyjo.Server.Prefork does, whose handlers only note a signal, is not written
    # to and does not wake the program up; a socket pair of the loop relays what Python writes on a signal to both, and a
    # signal that comes before the relay, which wakes only uvloop up, wakes the program up with a null byte, as
    # set_wakeup_fd does
    def _relayed(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return super().run_forever()
        wakeup = signal.set_wakeup_fd(-1)
        signal.set_wakeup_fd(wakeup)
        if wakeup < 0:
            return super().run_forever()

        if (pair := self._relay) is None:
            pair = self._relay = socket.socketpair()
            for sock in pair:
                sock.setblocking(False)
        reader, writer = pair
        fds = [wakeup]

        def relay() -> None:
            try:
                data = reader.recv(4096)
            except OSError:
                return
            for fd in fds:
                try:
                    os.write(fd, data)
                except OSError:
                    pass

        def install() -> None:
            fds.append(signal.set_wakeup_fd(writer.fileno(), warn_on_full_buffer=False))
            self.add_reader(reader, relay)
            try:
                os.write(wakeup, b'\0')
            except OSError:
                pass

        handle = self.call_soon(install)
        try:
            return super().run_forever()
        finally:
            handle.cancel()
            if not self.is_closed():
                self.remove_reader(reader)

    # The finalizer of an async generator, which a dealloc calls while CPython clears a frame, in Python, as the one of
    # asyncio: the handle of uvloop takes the stack in the debug mode with sys._getframe, which crashes on the frame
    # that is cleared when the hook of Cython is the top of the stack (MagicStack/uvloop#756)
    def _asyncgen_finalizer_hook(self, agen: Any) -> None:
        super()._asyncgen_finalizer_hook(agen)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    def close(self) -> None:
        super().close()
        if (pair := self._relay) is not None:
            self._relay = None
            for sock in pair:
                sock.close()


def _fileno(fd: Any) -> int:
    return fd if isinstance(fd, int) else fd.fileno()


def _blocking(fd: int) -> bool:
    try:
        return os.get_blocking(fd)
    except OSError:
        return False


# The threshold of a slow callback of PYJO_ASYNCIO_SLOW_CALLBACK, as for a loop of its own of Pyjo.Reactor.Asyncio
def _new_event_loop() -> asyncio.AbstractEventLoop:
    loop = _Loop()
    if duration := os.environ.get('PYJO_ASYNCIO_SLOW_CALLBACK'):
        loop.slow_callback_duration = float(duration)
    return loop


new = Pyjo_Reactor_Uvloop.new
object = Pyjo_Reactor_Uvloop
Uvloop = Pyjo_Reactor_Uvloop
