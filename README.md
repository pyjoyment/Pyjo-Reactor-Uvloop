[![Home](https://img.shields.io/badge/%F0%9F%8F%A0-Pyjoyment-02a7a0)](https://github.com/pyjoyment/Pyjoyment)
[![GitHub](https://img.shields.io/github/stars/pyjoyment/Pyjo-Reactor-Uvloop?style=flat&label=GitHub%20%E2%AD%90&logo=github)](https://github.com/pyjoyment/Pyjo-Reactor-Uvloop)
[![Documentation](https://img.shields.io/badge/docs-Read_the_Docs-blue?logo=readthedocs&logoColor=white)](https://pyjoyment.readthedocs.io/projects/pyjo-reactor-uvloop/en/stable/)
[![License](https://img.shields.io/github/license/pyjoyment/Pyjo-Reactor-Uvloop.svg)](https://github.com/pyjoyment/Pyjo-Reactor-Uvloop/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/Pyjo-Reactor-Uvloop?logo=pypi&logoColor=white)](https://pypi.org/project/Pyjo-Reactor-Uvloop/)
[![Tests](https://github.com/pyjoyment/Pyjo-Reactor-Uvloop/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/pyjoyment/Pyjo-Reactor-Uvloop/actions/workflows/tests.yaml)

# Pyjo-Reactor-Uvloop

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/pyjoyment/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-white-4x.png">
    <img src="https://raw.githubusercontent.com/pyjoyment/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-black-4x.png" alt="Pyjoyment" width="322">
  </picture>
</p>

Low level event reactor with [uvloop](https://uvloop.readthedocs.io) support
for [Pyjoyment](https://github.com/pyjoyment/Pyjoyment).

`Pyjo.Reactor.Uvloop` is `Pyjo.Reactor.Asyncio` with an event loop of its own
of uvloop, the event loop of asyncio on libuv, so that the servers of
Pyjoyment, `daemon`, `prefork` and `prethread`, and the blocking requests of
its user agent run on uvloop, with coroutines, tasks and the libraries of
asyncio along with them.

## Installation

From [PyPI](https://pypi.org/project/Pyjo-Reactor-Uvloop/), with
[Pyjoyment](https://pypi.org/project/Pyjoyment/) and
[uvloop](https://pypi.org/project/uvloop/), which it depends on, on Linux and
macOS, with CPython:

```sh
pip install Pyjo-Reactor-Uvloop
```

or, in a project managed with [uv](https://docs.astral.sh/uv/):

```sh
uv add Pyjo-Reactor-Uvloop
```

The development version is installed from the Git repository:

```sh
pip install git+https://github.com/pyjoyment/Pyjo-Reactor-Uvloop
```

## Usage

Select the reactor with `PYJO_REACTOR` before `Pyjo.IOLoop` is loaded:

```sh
PYJO_REACTOR=Pyjo.Reactor.Uvloop python myapp.py daemon
PYJO_REACTOR=Pyjo.Reactor.Uvloop python myapp.py prefork
```

The reactor takes the event loop that is running, as `Pyjo.Reactor.Asyncio`
does, so an ASGI server on uvloop, as `uvicorn --loop uvloop` or
`hypercorn --worker-class uvloop`, runs a Pyjoyment application on uvloop
with the default reactor already, and needs no reactor of uvloop.

## Examples

`examples/hello_world_uvloop.py` runs `Pyjo.HelloWorld` on the server of
Pyjoyment on uvloop until the signal `INT` or `TERM`, in a `with` block,
which closes the listen sockets of the server at its end:

```python
import os


# The reactor of Pyjoyment on uvloop, selected before Pyjo.IOLoop is loaded
os.environ['PYJO_REACTOR'] = 'Pyjo.Reactor.Uvloop'

import Pyjo.HelloWorld  # noqa: E402
import Pyjo.Server.Daemon  # noqa: E402


# The server of Pyjoyment on uvloop, until the signal INT or TERM, which closes its listen sockets at the end of the block
with Pyjo.Server.Daemon.new(app=Pyjo.HelloWorld.new(), listen=['http://*:3000']) as daemon:
    daemon.run()
```

```console
$ python examples/hello_world_uvloop.py
Web application available at http://127.0.0.1:3000
```

```console
$ curl http://127.0.0.1:3000/
Your Pyjo is working!
```

`examples/asyncio_uvloop.py` is a coroutine on the loop of uvloop, which
requests the server of Pyjoyment in the same loop with the streams of asyncio
and with the user agent of Pyjoyment, as the libraries of asyncio run along
with the reactor:

```python
import os


# The reactor of Pyjoyment on uvloop, selected before Pyjo.IOLoop is loaded
os.environ['PYJO_REACTOR'] = 'Pyjo.Reactor.Uvloop'

import Pyjo.HelloWorld  # noqa: E402
import Pyjo.IOLoop  # noqa: E402
import Pyjo.Server.Daemon  # noqa: E402
import Pyjo.UserAgent  # noqa: E402

import asyncio  # noqa: E402

import uvloop  # noqa: E402


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

    return 'uvloop' if isinstance(asyncio.get_running_loop(), uvloop.Loop) else 'asyncio'


# The server, on a port that the system picks, which closes its listen sockets at the end of the block
with Pyjo.Server.Daemon.new(app=Pyjo.HelloWorld.new(), listen=['http://127.0.0.1'], silent=True) as daemon:
    port = daemon.start().ports()[0]
    Pyjo.IOLoop.singleton.reactor.run_coroutine(
        main(port),
        lambda loop: (print(f'loop: {loop}'), Pyjo.IOLoop.stop()),
        lambda err: (print(f'error: {err}'), Pyjo.IOLoop.stop()),
    )
    Pyjo.IOLoop.start()
```

```console
$ python examples/asyncio_uvloop.py
asyncio: HTTP/1.1 200 OK
Pyjo.UserAgent: 200 Your Pyjo is working!
loop: uvloop
```

`examples/loopback_uvloop.py` is a server of Pyjoyment and its user agent on
the loop of uvloop, a blocking request, which runs the event loop until the
response, and the class of the reactor and whether its loop is one of uvloop, which
Build checks with the wheel:

```python
import os


# The reactor of Pyjoyment on uvloop, selected before Pyjo.IOLoop is loaded
os.environ['PYJO_REACTOR'] = 'Pyjo.Reactor.Uvloop'

import Pyjo.HelloWorld  # noqa: E402
import Pyjo.IOLoop  # noqa: E402
import Pyjo.Server.Daemon  # noqa: E402
import Pyjo.UserAgent  # noqa: E402

import uvloop  # noqa: E402


# The server, on a port that the system picks, and the user agent, in the same event loop, which close their sockets at
# the end of the block
with (
    Pyjo.Server.Daemon.new(app=Pyjo.HelloWorld.new(), listen=['http://127.0.0.1'], silent=True) as daemon,
    Pyjo.UserAgent.new(ioloop=Pyjo.IOLoop.singleton) as ua,
):
    # A blocking request, which runs the event loop of the server on uvloop until the response
    tx = ua.get(f'http://127.0.0.1:{daemon.start().ports()[0]}/')
    reactor = Pyjo.IOLoop.singleton.reactor
    print(type(reactor).__name__, 'uvloop' if isinstance(reactor.loop, uvloop.Loop) else 'asyncio')
    print(tx.result.code, tx.result.text)
```

```console
$ python examples/loopback_uvloop.py
Pyjo_Reactor_Uvloop uvloop
200 Your Pyjo is working!
```

## Documentation

The API of the module and the examples are on
[Read the Docs](https://pyjoyment.readthedocs.io/projects/pyjo-reactor-uvloop/en/stable/).

## Status

A reactor of Pyjoyment in a distribution of its own, as
[Pyjo-Reactor-Twisted](https://github.com/pyjoyment/Pyjo-Reactor-Twisted).

## License

The Artistic License 2.0, as Pyjoyment.
