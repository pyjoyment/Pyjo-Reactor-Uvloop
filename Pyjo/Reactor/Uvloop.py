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
reactor moves to a new loop of its own of uvloop.

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


# The threshold of a slow callback of PYJO_ASYNCIO_SLOW_CALLBACK, as for a loop of its own of Pyjo.Reactor.Asyncio
def _new_event_loop() -> asyncio.AbstractEventLoop:
    loop = uvloop.new_event_loop()
    if duration := os.environ.get('PYJO_ASYNCIO_SLOW_CALLBACK'):
        loop.slow_callback_duration = float(duration)
    return loop


new = Pyjo_Reactor_Uvloop.new
object = Pyjo_Reactor_Uvloop
Uvloop = Pyjo_Reactor_Uvloop
