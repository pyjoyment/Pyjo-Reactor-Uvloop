import os


# The reactor of Pyjoyment on uvloop, selected before Pyjo.IOLoop is loaded
os.environ['PYJO_REACTOR'] = 'Pyjo.Reactor.Uvloop'

import Pyjo.HelloWorld  # noqa: E402
import Pyjo.IOLoop  # noqa: E402
import Pyjo.Server.Daemon  # noqa: E402
import Pyjo.UserAgent  # noqa: E402

import asyncio  # noqa: E402


# A coroutine on the loop of uvloop, with the streams of asyncio and the user agent of Pyjoyment, both requesting the
# server of Pyjoyment in the same loop
async def main(port):
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    writer.write(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n')
    print(f'asyncio: {(await reader.readline()).decode().strip()}')
    writer.close()
    await writer.wait_closed()

    with Pyjo.UserAgent.new() as ua:
        tx = await ua.get_p(f'http://127.0.0.1:{port}/')
        print(f'Pyjo.UserAgent: {tx.res.code} {tx.res.text}')

    return type(asyncio.get_running_loop()).__module__


# The server, on a port that the system picks, which closes its listen sockets at the end of the block
with Pyjo.Server.Daemon.new(app=Pyjo.HelloWorld.new(), listen=['http://127.0.0.1'], silent=True) as daemon:
    port = daemon.start().ports()[0]
    Pyjo.IOLoop.singleton.reactor.run_coroutine(
        main(port),
        lambda loop: (print(f'loop: {loop}'), Pyjo.IOLoop.stop()),
        lambda err: (print(f'error: {err}'), Pyjo.IOLoop.stop()),
    )
    Pyjo.IOLoop.start()
