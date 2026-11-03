from Pyjo.Test import *

import contextlib
import io
import socket


# The synopsis of the module in both forms, as t/docs of Pyjoyment checks the synopsis of each module
with subtest('Synopsis'):
    first, peer = socket.socketpair()
    second, other = socket.socketpair()
    fd = second.fileno()
    other.sendall(b'x')

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        from Pyjo.Reactor.Uvloop import Uvloop

        # Watch if handle becomes readable or writable
        reactor = Uvloop()
        reactor.io(
            first,
            lambda reactor, writable: print('First handle is writable' if writable else 'First handle is readable'),
        )

        reactor.one_tick()
        reactor.remove(first)
    ok('First handle is writable' in output.getvalue().splitlines(), 'first handle')
    reactor.close()

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        # Or import the module, as in Google Python Style Guide

        import Pyjo.Reactor.Uvloop

        # Watch if handle becomes readable or writable
        reactor = Pyjo.Reactor.Uvloop.new()
        reactor.io(
            first,
            lambda reactor, writable: print('First handle is writable' if writable else 'First handle is readable'),
        )

        # Change to watching only if handle becomes writable
        reactor.watch(first, False, True)

        # Watch a file descriptor if it becomes readable
        reactor.io(
            fd,
            lambda reactor, writable: print('Second handle is writable' if writable else 'Second handle is readable'),
        ).watch(fd, True, False)

        # Add a timer
        def timeout(reactor):
            reactor.remove(first)
            reactor.remove(fd)
            print('Timeout!')

        reactor.timer(0.05, timeout)

        # Start reactor if necessary
        if not reactor.is_running:
            reactor.start()
    lines = output.getvalue().splitlines()
    ok('First handle is writable' in lines, 'first handle')
    ok('Second handle is readable' in lines, 'second handle')
    is_ok(lines[-1], 'Timeout!', 'timeout')
    ok('First handle is readable' not in lines, 'not readable')
    for sock in (first, peer, second, other):
        sock.close()
    reactor.close()

done_testing()
