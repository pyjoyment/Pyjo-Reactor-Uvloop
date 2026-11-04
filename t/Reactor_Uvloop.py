import os


# Unlike Mojolicious: the reactor of the test is selected before Pyjo.IOLoop is loaded, as Mojo::Reactor->detect prefers
# Mojo::Reactor::EV where it is installed, and Pyjo.Reactor.detect() prefers Pyjo.Reactor.Asyncio
os.environ['PYJO_REACTOR'] = 'Pyjo.Reactor.Uvloop'

import Pyjo.Reactor  # noqa: E402
import Pyjo.Reactor.Asyncio  # noqa: E402
import Pyjo.Reactor.Uvloop  # noqa: E402

from Pyjo.Loader import load_class  # noqa: E402
from Pyjo.Test import *  # noqa: E402

import asyncio  # noqa: E402
import signal  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import uvloop  # noqa: E402


def eval_(cb):
    try:
        cb()
    except Exception as e:
        return e


# Shared between subtests, since I/O watchers and timers keep firing across them
readable = writable = 0


def rw_cb(reactor, is_writable):
    global readable, writable
    if is_writable:
        writable += 1
    else:
        readable += 1


with subtest('Instantiation'):
    reactor = Pyjo.Reactor.Uvloop.new()
    is_ok(type(reactor), Pyjo.Reactor.Uvloop.object, 'right object')
    is_ok(type(Pyjo.Reactor.Uvloop.new()), Pyjo.Reactor.Uvloop.object, 'right object')
    del reactor
    is_ok(type(Pyjo.Reactor.Uvloop.new()), Pyjo.Reactor.Uvloop.object, 'right object')
    # Not in Mojolicious: the constructor of Python, as in Pyjoyment, and the reactor of asyncio, which it extends
    is_ok(Pyjo.Reactor.Uvloop.Uvloop, Pyjo.Reactor.Uvloop.object, 'right class')
    is_ok(type(Pyjo.Reactor.Uvloop.Uvloop()), Pyjo.Reactor.Uvloop.object, 'right object')
    ok(issubclass(Pyjo.Reactor.Uvloop.object, Pyjo.Reactor.Asyncio.object), 'reactor of asyncio')
    ok(not load_class('Pyjo.IOLoop'), 'use Pyjo.IOLoop')
    reactor = Pyjo.IOLoop.singleton.reactor
    is_ok(type(reactor), Pyjo.Reactor.Uvloop.object, 'right object')

with subtest('Make sure it stops automatically when not watching for events'):
    triggered = 0

    def triggered_cb(loop):
        global triggered
        triggered += 1

    Pyjo.IOLoop.next_tick(triggered_cb)
    Pyjo.IOLoop.start()
    ok(triggered, 'reactor waited for one event')
    started = time.time()
    Pyjo.IOLoop.start()
    Pyjo.IOLoop.one_tick()
    ok(time.time() < (started + 10), 'stopped automatically')

with subtest('Listen'):
    listen = socket.create_server(('127.0.0.1', 0), backlog=5)
    port = listen.getsockname()[1]
    reactor.io(listen, rw_cb).watch(listen, False, False).watch(listen, True, True)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(not readable, 'handle is not readable')
    ok(not writable, 'handle is not writable')

with subtest('Connect'):
    client = socket.create_connection(('127.0.0.1', port))
    reactor.timer(1, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable')
    ok(not writable, 'handle is not writable')

with subtest('Accept'):
    server = listen.accept()[0]
    ok(reactor.remove(listen), 'removed')
    ok(not reactor.remove(listen), 'not removed again')
    readable = writable = 0
    reactor.io(client, rw_cb)
    reactor.again(reactor.timer(0.025, lambda reactor: reactor.stop()))
    reactor.start()
    ok(not readable, 'handle is not readable')
    ok(writable, 'handle is writable')
    client.sendall(b'hello!\n')
    time.sleep(1)
    ok(reactor.remove(client), 'removed')
    readable = writable = 0
    reactor.io(server, rw_cb)
    reactor.watch(server, True, False)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable')
    ok(not writable, 'handle is not writable')
    readable = writable = 0
    reactor.watch(server, True, True)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable')
    ok(writable, 'handle is writable')
    readable = writable = 0
    reactor.watch(server, False, False)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(not readable, 'handle is not readable')
    ok(not writable, 'handle is not writable')
    readable = writable = 0
    reactor.watch(server, True, False)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable')
    ok(not writable, 'handle is not writable')
    readable = writable = 0
    reactor.io(server, rw_cb)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable')
    ok(writable, 'handle is writable')

with subtest('Timers'):
    timer = recurring = 0

    def timer_cb(reactor):
        global timer
        timer += 1

    def recurring_cb(reactor):
        global recurring
        recurring += 1

    reactor.timer(0, timer_cb)
    ok(reactor.remove(reactor.timer(0, timer_cb)), 'removed')
    id = reactor.recurring(0, recurring_cb)
    readable = writable = 0
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable again')
    ok(writable, 'handle is writable again')
    ok(timer, 'timer was triggered')
    ok(recurring, 'recurring was triggered')
    done = False
    readable = writable = timer = recurring = 0

    def done_cb(reactor):
        global done
        done = reactor.is_running

    reactor.timer(0.025, done_cb)
    while not done:
        reactor.one_tick()
    ok(readable, 'handle is readable again')
    ok(writable, 'handle is writable again')
    ok(not timer, 'timer was not triggered')
    ok(recurring, 'recurring was triggered again')
    readable = writable = timer = recurring = 0
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable again')
    ok(writable, 'handle is writable again')
    ok(not timer, 'timer was not triggered')
    ok(recurring, 'recurring was triggered again')
    ok(reactor.remove(id), 'removed')
    ok(not reactor.remove(id), 'not removed again')
    readable = writable = timer = recurring = 0
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable again')
    ok(writable, 'handle is writable again')
    ok(not timer, 'timer was not triggered')
    ok(not recurring, 'recurring was not triggered again')
    readable = writable = timer = recurring = 0
    next_tick = 0

    def next_tick_cb(reactor):
        global next_tick
        next_tick += 1

    is_ok(reactor.next_tick(next_tick_cb), None, 'returned None')
    id = reactor.recurring(0, recurring_cb)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(readable, 'handle is readable again')
    ok(writable, 'handle is writable again')
    ok(not timer, 'timer was not triggered')
    ok(recurring, 'recurring was triggered again')
    ok(next_tick, 'next tick was triggered')

with subtest('Reset'):

    def reset_failed_cb(reactor):
        raise Exception('Reset failed')

    reactor.next_tick(reset_failed_cb)
    reactor.reset()
    readable = writable = recurring = 0
    reactor.next_tick(lambda reactor: reactor.stop())
    reactor.start()
    ok(not readable, 'io event was not triggered again')
    ok(not writable, 'io event was not triggered again')
    ok(not recurring, 'recurring was not triggered again')
    reactor2 = Pyjo.Reactor.Uvloop.new()
    is_ok(type(reactor2), Pyjo.Reactor.Uvloop.object, 'right object')

with subtest('Ordered next_tick'):
    result = []
    for i in range(1, 11):
        reactor.next_tick(lambda reactor, i=i: result.append(i))
    reactor.start()
    is_deeply_ok(result, list(range(1, 11)), 'right result')

with subtest('Reset while watchers are active'):
    writable = 0

    def reset_cb(reactor, is_writable):
        global writable
        writable += 1
        reactor.reset()

    for handle in (client, server):
        reactor.io(handle, reset_cb).watch(handle, False, True)
    reactor.start()
    is_ok(writable, 1, 'only one handle was writable')
    client.close()
    server.close()

with subtest('Concurrent reactors'):
    timer = 0
    reactor.recurring(0, timer_cb)
    timer2 = 0

    def timer2_cb(reactor):
        global timer2
        timer2 += 1

    reactor2.recurring(0, timer2_cb)
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(timer, 'timer was triggered')
    ok(not timer2, 'timer was not triggered')
    timer = timer2 = 0
    reactor2.timer(0.025, lambda reactor: reactor.stop())
    reactor2.start()
    ok(not timer, 'timer was not triggered')
    ok(timer2, 'timer was triggered')
    timer = timer2 = 0
    reactor.timer(0.025, lambda reactor: reactor.stop())
    reactor.start()
    ok(timer, 'timer was triggered')
    ok(not timer2, 'timer was not triggered')
    timer = timer2 = 0
    reactor2.timer(0.025, lambda reactor: reactor.stop())
    reactor2.start()
    ok(not timer, 'timer was not triggered')
    ok(timer2, 'timer was triggered')
    reactor.reset()

with subtest('Restart timer'):
    single = pair = last = 0

    def single_cb(reactor):
        global single
        single += 1

    def one_cb(reactor):
        global pair, last
        if single and pair:
            last += 1
        pair += 1
        reactor.stop() if pair > 1 else reactor.again(two)

    def two_cb(reactor):
        global pair, last
        if single and pair:
            last += 1
        pair += 1
        reactor.stop() if pair > 1 else reactor.again(one)

    reactor.timer(0.025, single_cb)
    one = reactor.timer(0.025, one_cb)
    two = reactor.timer(0.025, two_cb)
    reactor.start()
    is_ok(pair, 2, 'timer pair was triggered')
    ok(single, 'single timer was triggered')
    ok(last, 'timers were triggered in the right order')

with subtest('Reset timer'):
    before = time.monotonic()
    after = None
    again = 0

    def after_cb(reactor):
        global after
        after = time.monotonic()

    def again_cb(reactor):
        global again
        again += 1
        if again > 3:
            reactor.remove(two)

    def restart_cb(reactor):
        reactor.again(one, 0.025)
        reactor.again(two, 0.025)

    one = reactor.timer(300, after_cb)
    two = reactor.recurring(300, again_cb)
    reactor.timer(0.025, restart_cb)
    reactor.start()
    ok(after, 'timer was triggered')
    ok((after - before) < 200, 'less than 200 seconds')
    is_ok(again, 4, 'recurring timer triggered four times')

with subtest('Restart inactive timer'):
    id = reactor.timer(0, lambda reactor: None)
    ok(reactor.remove(id), 'removed')
    err = eval_(lambda: reactor.again(id))
    like_ok(str(err), r'Timer not active', 'right error')

with subtest('Change inactive I/O watcher'):
    ok(not reactor.remove(listen), 'not removed again')
    err = eval_(lambda: reactor.watch(listen, True, True))
    like_ok(str(err), r'I/O watcher not active', 'right error')
    listen.close()

with subtest('Error'):
    err = None

    def error_cb(reactor, e):
        global err
        reactor.stop()
        err = e

    def die_cb(reactor):
        raise Exception('works!\n')

    reactor.unsubscribe('error').on('error', error_cb)
    reactor.timer(0, die_cb)
    reactor.start()
    like_ok(str(err), r'works!', 'right error')

    # Not in Mojolicious: the arguments of a callback, which Perl does not check, as in Pyjo.Reactor.Asyncio
    reactor.timer(0, lambda: None)
    reactor.start()
    like_ok(
        str(err),
        r'takes 0 positional arguments but 1 was given: the callbacks of a reactor get the reactor first',
        'hint',
    )

with subtest('Reset events'):
    reactor.on('error', lambda reactor, err: None)
    ok(reactor.has_subscribers('error'), 'has subscribers')
    reactor.reset()
    ok(not reactor.has_subscribers('error'), 'no subscribers')

with subtest('Recursion'):
    timer = 0

    def recursion_cb(reactor):
        global timer
        timer += 1
        reactor.one_tick()

    reactor = Pyjo.Reactor.Uvloop.new()
    reactor.timer(0, recursion_cb)
    reactor.one_tick()
    is_ok(timer, 1, 'timer was triggered once')

with subtest('Detection'):
    is_ok(Pyjo.Reactor.object.detect(), 'Pyjo.Reactor.Uvloop', 'right class')

with subtest('Reactor in control'):
    is_ok(type(Pyjo.IOLoop.singleton.reactor), Pyjo.Reactor.Uvloop.object, 'right object')
    ok(not Pyjo.IOLoop.is_running(), 'loop is not running')
    buffer = b''
    server_err = server_running = client_err = client_running = None

    def server_cb(loop, stream, cid):
        global server_err, server_running
        stream.write(b'test', lambda stream: stream.write(b'321'))
        server_running = Pyjo.IOLoop.is_running()
        server_err = eval_(lambda: Pyjo.IOLoop.start())

    id = Pyjo.IOLoop.server(server_cb, address='127.0.0.1')
    port = Pyjo.IOLoop.acceptor(id).port

    def client_cb(loop, err, stream):
        global client_err, client_running

        def read_cb(stream, chunk):
            global buffer
            buffer += chunk
            if buffer != b'test321':
                return
            Pyjo.IOLoop.singleton.reactor.stop()

        stream.on('read', read_cb)
        client_running = Pyjo.IOLoop.is_running()
        client_err = eval_(lambda: Pyjo.IOLoop.start())

    Pyjo.IOLoop.client(client_cb, port=port)
    Pyjo.IOLoop.singleton.reactor.start()
    ok(not Pyjo.IOLoop.is_running(), 'loop is not running')
    like_ok(str(server_err), r'^Pyjo.IOLoop already running', 'right error')
    like_ok(str(client_err), r'^Pyjo.IOLoop already running', 'right error')
    ok(server_running, 'loop is running')
    ok(client_running, 'loop is running')

# Left out from Mojolicious: the abstract methods of Mojo::Reactor, which t/Pyjo/Reactor_Asyncio.py of Pyjoyment tests

# Not in Mojolicious: a callback of next_tick from a signal handler, which Python runs in the middle of what the reactor
# does, as the servers stop gracefully, with enough timers that the handler interrupts the reactor while it handles
# them, as in Pyjo.Reactor.Asyncio
with subtest('next_tick from a signal handler'):
    if not hasattr(signal, 'setitimer'):
        plan(skip_all='signal.setitimer is required')
    reactor = Pyjo.Reactor.Uvloop.new()
    for _ in range(100000):
        reactor.timer(10, lambda reactor: None)
    ticks = []
    handler = signal.signal(signal.SIGALRM, lambda signum, frame: reactor.next_tick(lambda reactor: ticks.append(1)))
    signal.setitimer(signal.ITIMER_REAL, 0.001, 0.001)
    reactor.timer(0.3, lambda reactor: reactor.stop())
    try:
        err = eval_(lambda: reactor.start())
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, handler)
    is_ok(err, None, 'no error')
    ok(ticks, 'callbacks of the signal handler')
    reactor.reset()
    reactor.close()

# Not in Mojolicious: the loop of uvloop, which is what the reactor adds to Pyjo.Reactor.Asyncio
with subtest('Loop of its own of uvloop'):
    with Pyjo.Reactor.Uvloop.new() as reactor:
        loop = reactor.loop
        ok(isinstance(loop, uvloop.Loop), 'loop of uvloop')
        ok(isinstance(loop, asyncio.AbstractEventLoop), 'loop of asyncio')
        is_ok(reactor.loop, loop, 'same loop')
        fired = []
        reactor.timer(
            0, lambda reactor: (fired.append(isinstance(asyncio.get_running_loop(), uvloop.Loop)), reactor.stop())
        )
        reactor.start()
        is_deeply_ok(fired, [True], 'timer in the loop of uvloop')
    ok(loop.is_closed(), 'loop closed at the end of the block')
    with Pyjo.Reactor.Asyncio.new() as reactor:
        ok(not isinstance(reactor.loop, uvloop.Loop), 'the reactor of asyncio keeps the loop of asyncio')

with subtest('Loop that the reactor is given'):
    loop = asyncio.new_event_loop()
    reactor = Pyjo.Reactor.Uvloop.new(loop=loop)
    is_ok(reactor.loop, loop, 'loop of asyncio that it is given')
    reactor.close()
    ok(not loop.is_closed(), 'loop that it is given not closed')
    loop.close()

# As inside an ASGI server, which runs the loop itself: the reactor takes the loop that is running, of asyncio or of uvloop
with subtest('Loop that is running'):

    async def running():
        reactor = Pyjo.Reactor.Uvloop.new()
        return reactor.loop is asyncio.get_running_loop(), isinstance(reactor.loop, uvloop.Loop)

    is_deeply_ok(asyncio.run(running()), (True, False), 'loop of asyncio that is running, not one of uvloop')
    is_deeply_ok(uvloop.run(running()), (True, True), 'loop of uvloop that is running')

with subtest('Coroutine on the loop of uvloop'):

    async def coroutine():
        await asyncio.sleep(0.01)
        return isinstance(asyncio.get_running_loop(), uvloop.Loop)

    with Pyjo.Reactor.Uvloop.new() as reactor:
        result = []
        reactor.run_coroutine(
            coroutine(),
            lambda value: (result.append(value), reactor.stop()),
            lambda err: (result.append(err), reactor.stop()),
        )
        reactor.start()
        is_deeply_ok(result, [True], 'coroutine of asyncio on the loop of uvloop')

with subtest('Threshold of a slow callback'):
    os.environ['PYJO_ASYNCIO_SLOW_CALLBACK'] = '5'
    try:
        with Pyjo.Reactor.Uvloop.new() as reactor:
            is_ok(reactor.loop.slow_callback_duration, 5.0, 'from PYJO_ASYNCIO_SLOW_CALLBACK')
    finally:
        del os.environ['PYJO_ASYNCIO_SLOW_CALLBACK']

# Not in Mojolicious: the child of a fork, as a worker of Pyjo.Server.Prefork, gets a new loop of its own of uvloop, as
# the one of the parent is not the child's
with subtest('Fork'):
    if not hasattr(os, 'fork'):
        plan(skip_all='os.fork is required')
    with Pyjo.Reactor.Uvloop.new() as reactor:
        parent = reactor.loop
        read, write = os.pipe()
        pid = os.fork()
        if not pid:
            os.close(read)
            try:
                child = reactor.loop
                fired = []
                reactor.timer(0, lambda reactor: (fired.append(1), reactor.stop()))
                reactor.start()
                status = 0 if isinstance(child, uvloop.Loop) and child is not parent and fired else 1
            except BaseException:
                status = 2
            os.write(write, str(status).encode())
            os._exit(status)
        os.close(write)
        with os.fdopen(read) as file:
            child_status = file.read()
        _, status = os.waitpid(pid, 0)
        is_ok(child_status, '0', 'new loop of uvloop in the child, with a timer')
        is_ok(os.waitstatus_to_exitcode(status), 0, 'child exited')
        is_ok(reactor.loop, parent, 'loop of the parent kept')

# Not in Mojolicious: a child of a fork that ends at the exit of the interpreter, as the manager of Pyjo.Server.Hot, which
# removes its process id file then; the loop of the parent is not closed in the child, where libuv aborts on it
with subtest('Exit of the child of a fork'):
    if not hasattr(os, 'fork'):
        plan(skip_all='os.fork is required')
    code = """
import os, sys
import Pyjo.Reactor.Uvloop
reactor = Pyjo.Reactor.Uvloop.new()
reactor.timer(0, lambda reactor: reactor.stop())
reactor.start()
pid = os.fork()
if not pid:
    reactor.timer(0, lambda reactor: reactor.stop())
    reactor.start()
    sys.exit(0)
print(os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]))
"""
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    is_ok(result.stdout, '0\n', 'child exited at the end of the interpreter')
    is_ok(result.stderr, '', 'nothing on the standard error')

# Not in Mojolicious: the wakeup fd of the signals that the program sets, as a worker of Pyjo.Server.Prefork does, whose
# handler only notes the signal, which a watcher of the socket of the wakeup fd handles
with subtest('Wakeup fd of the signals'):
    if not hasattr(signal, 'SIGUSR1'):
        plan(skip_all='SIGUSR1 is required')
    noted = []
    woken = []
    handler = signal.signal(signal.SIGUSR1, lambda signum, frame: noted.append(signum))
    waker, wakee = socket.socketpair()
    waker.setblocking(False)
    wakee.setblocking(False)
    wakeup = signal.set_wakeup_fd(waker.fileno())
    try:
        with Pyjo.Reactor.Uvloop.new() as reactor:

            def wake(reactor, writable):
                wakee.recv(4096)
                if noted:
                    woken.extend(noted)
                    reactor.stop()

            reactor.io(wakee, wake).watch(wakee, True, False)
            reactor.timer(0.1, lambda reactor: os.kill(os.getpid(), signal.SIGUSR1))
            reactor.timer(5, lambda reactor: reactor.stop())
            reactor.start()
            reactor.remove(wakee)
    finally:
        signal.set_wakeup_fd(wakeup)
        signal.signal(signal.SIGUSR1, handler)
        waker.close()
        wakee.close()
    is_deeply_ok(woken, [signal.SIGUSR1], 'socket of the wakeup fd written to on the signal')
    is_ok(signal.set_wakeup_fd(wakeup), wakeup, 'wakeup fd set back')

# Not in Mojolicious: an async generator that the end of another one frees, whose finalizer uvloop calls while CPython
# clears the frame, in the debug mode of asyncio, which crashed the interpreter, so in a process of its own
with subtest('Finalizer of an async generator in the debug mode'):
    code = """
import Pyjo.Reactor.Uvloop


async def numbers():
    for i in range(10):
        yield i


async def head(n):
    it = numbers()
    while n > 0:
        n -= 1
        yield await anext(it)


async def main():
    return [[e async for e in head(2)] for _ in range(100)][-1]


reactor = Pyjo.Reactor.Uvloop.new()
reactor.loop.set_debug(True)
result = []
reactor.run_coroutine(main(), lambda value: (result.append(value), reactor.stop()), lambda err: (result.append(err), reactor.stop()))
reactor.start()
print(result)
"""
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    is_ok(result.returncode, 0, 'no crash')
    is_ok(result.stdout, '[[0, 1]]\n', 'right result')

# Not in Mojolicious: after stop, the loop of uvloop polls once more, which would call a writer that stops it again in
# the same run, where the loop of asyncio ends after the callbacks of its select
with subtest('Stop in a callback of I/O'):
    a, b = socket.socketpair()
    with Pyjo.Reactor.Uvloop.new() as reactor:
        calls = []

        def stopping(reactor, writable):
            calls.append(writable)
            reactor.stop()

        reactor.io(a, stopping).watch(a, False, True)
        reactor.start()
        is_deeply_ok(calls, [True], 'one event before the stop')
        reactor.start()
        is_deeply_ok(calls, [True, True], 'one event in the next run')
        calls.clear()
        reactor.recurring(0, lambda reactor: None)
        for _ in range(3):
            reactor.one_tick()
        ok(len(calls) >= 1, 'no starving of I/O by a timer of no time in one_tick')
        reactor.remove(a)
    a.close()
    b.close()

# Not in Mojolicious: libuv sets a handle that it watches to the non-blocking mode, which a terminal shares with the shell
with subtest('Blocking mode of a handle'):
    read, write = os.pipe()
    with Pyjo.Reactor.Uvloop.new() as reactor:
        reactor.io(read, lambda reactor, writable: None).watch(read, True, False)
        reactor.io(write, lambda reactor, writable: None).watch(write, False, True)
        ok(os.get_blocking(read) and os.get_blocking(write), 'blocking while watched')
        reactor.remove(read)
        reactor.remove(write)
        ok(os.get_blocking(read) and os.get_blocking(write), 'blocking after')
    os.close(read)
    os.close(write)

# Not in Mojolicious: on an error of a handle, libuv of Linux calls its writer once and uvloop does not watch it anymore,
# where the loop of asyncio calls it for as long as the error lasts
with subtest('Writer of a pipe whose reader has closed it'):
    read, write = os.pipe()
    os.set_blocking(write, False)
    with Pyjo.Reactor.Uvloop.new() as reactor:
        calls = []

        def writer(reactor, writable):
            calls.append(writable)
            if len(calls) == 1:
                os.close(read)

        reactor.io(write, writer).watch(write, False, True)
        reactor.timer(0.1, lambda reactor: reactor.stop())
        reactor.start()
        ok(len(calls) > 2, 'writer called again after the error')
        reactor.remove(write)
    os.close(write)

done_testing()
