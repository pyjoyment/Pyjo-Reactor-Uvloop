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
its own.

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
import os
import signal
import socket
import threading
import weakref

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

    # The loop of the parent stays in the loops of their own of Pyjo.Reactor.Asyncio in the child of a fork, which closes
    # it at the exit, where libuv aborts on the kqueue of the parent
    def _fork(self) -> None:
        old = self._loop
        super()._fork()  # pyright: ignore[reportUnknownMemberType]
        if old is not None and self._loop is not old:
            Pyjo.Reactor.Asyncio._OWN.discard(old)  # pyright: ignore[reportPrivateUsage]


# uvloop sets the wakeup fd of the signals to a socket of its own while it runs, in the main thread, so that the one that
# the program has set, as a worker of Pyjo.Server.Prefork does, whose handlers only note a signal, is not written to and
# does not wake the program up; a socket pair of the loop relays what Python writes on a signal to both, and a signal
# that comes before the relay, which wakes only uvloop up, wakes the program up with a null byte, as set_wakeup_fd does
class _Loop(uvloop.Loop):  # pyright: ignore[reportUntypedBaseClass]
    _relay: tuple[socket.socket, socket.socket] | None = None

    def run_forever(self) -> None:
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

    def close(self) -> None:
        super().close()
        if (pair := self._relay) is not None:
            self._relay = None
            for sock in pair:
                sock.close()


# The threshold of a slow callback of PYJO_ASYNCIO_SLOW_CALLBACK, as for a loop of its own of Pyjo.Reactor.Asyncio
def _new_event_loop() -> asyncio.AbstractEventLoop:
    loop = _Loop()
    if duration := os.environ.get('PYJO_ASYNCIO_SLOW_CALLBACK'):
        loop.slow_callback_duration = float(duration)
    return loop


new = Pyjo_Reactor_Uvloop.new
object = Pyjo_Reactor_Uvloop
Uvloop = Pyjo_Reactor_Uvloop
