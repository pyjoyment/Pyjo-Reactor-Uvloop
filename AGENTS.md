# Agent Guide: Pyjo-Reactor-Uvloop

## Overview

`Pyjo.Reactor.Uvloop` is a reactor of Pyjoyment on the event loop of uvloop, in
a distribution of its own, as every reactor of Pyjoyment with a dependency is:
Pyjoyment has no runtime dependencies, and one reactor does not pull the
dependencies of another. The conventions are those of Pyjoyment: read its
`AGENTS.md` in the checkout next to this one, `../Pyjoyment/AGENTS.md`. The
repository is made of the one of Pyjo-Reactor-Twisted, whose workflows and
linters it shares.

## How it works

- It is a subclass of `Pyjo.Reactor.Asyncio`, as the loop of uvloop is a loop
  of asyncio, which overrides `_own_loop`, the loop that the reactor makes for
  itself: a subclass of `uvloop.Loop` in the place of
  `asyncio.new_event_loop()`. The rest of what the reactor does with a loop of
  its own, which `_own_loop` repeats, the set of the loops that are closed at
  the exit of the interpreter, the finalizer that closes the loop with the
  reactor and its handler of `atexit`, are private members of
  `Pyjo.Reactor.Asyncio`, so a change of them in Pyjoyment breaks the reactor:
  the suite of Pyjoyment, which CI runs on the reactor, is what guards them.
- What the reactor is for is the servers of Pyjoyment, `daemon`, `prefork` and
  `prethread`, and its blocking user agent, where no loop runs and the reactor
  makes one. An ASGI server on uvloop, as uvicorn and Hypercorn, runs the loop
  itself with `loop_factory=uvloop.new_event_loop`, which
  `Pyjo.Reactor.Asyncio` takes already, as `t/servers/ASGI.py` of Pyjoyment
  tests, and a given loop or a loop that is running is taken by this reactor
  too, of asyncio or of uvloop.
- uvloop sets the wakeup fd of the signals, `signal.set_wakeup_fd`, to a
  socket of its own in `run_forever`, in the main thread, and sets the old one
  back when the loop stops, where the loop of asyncio sets one only for
  `add_signal_handler`. A worker of `Pyjo.Server.Prefork` sets a socket pair
  as the wakeup fd and watches it with the reactor, as its handlers of TERM and
  QUIT only note the signal, so on the plain loop of uvloop the handler runs,
  but the worker is never woken up to handle it and does not stop. The loop of
  the reactor, `_Loop`, relays: while it runs, a socket pair of its own is the
  wakeup fd, whose bytes it writes to both the socket of uvloop, for
  `add_signal_handler`, and the wakeup fd of the program, with a null byte at
  the start for a signal that came before the relay. A signal handler of
  Python still runs when uvloop calls `PyErr_CheckSignals`.
- The child of a fork, as a worker of `Pyjo.Server.Prefork`, moves to a new
  loop of its own, which `_fork` of `Pyjo.Reactor.Asyncio` makes with
  `_own_loop`, so of uvloop, as libuv of the parent is not the child's. `_fork`
  of Pyjoyment 0.2.0 leaves the loop of the parent in `_OWN`, so the child
  closes it at the exit of the interpreter: the loop of asyncio only reports
  the closed kqueue on macOS, while libuv aborts the child before its
  finalizers, as the one of `Pyjo.Server.Hot` that removes `hot.pid`. The
  reactor needs the `_fork` of pyjoyment/Pyjoyment#497, which keeps it out of
  `_OWN`, so Pyjoyment 0.3.0 at least.
- In the debug mode of asyncio, which CI runs with `PYTHONDEVMODE=1`, a handle
  of uvloop takes the stack where it is made, with `sys._getframe` of Cython.
  The finalizer of an async generator that the end of another one frees, as
  `head` of `Pyjo.Iterator` does, runs while CPython clears that frame, and
  the hook of uvloop, `_asyncgen_finalizer_hook`, of Cython too, makes a
  handle there, so `sys._getframe` reads the frame that is cleared and crashes
  the interpreter, from CPython 3.12 to 3.15. `_Loop` overrides the hook in
  Python, which the stack starts from then, as the hook of asyncio does, until
  MagicStack/uvloop#756, which fixes it in uvloop, is released.
- After `stop`, uvloop ends the iteration of libuv, so a stop in a callback of
  I/O goes on to the poll of the next iteration, which calls the readers and
  the writers that are ready again; the loop of asyncio ends with the
  callbacks of its select. An event of the reactor that stops it, or ends
  `one_tick`, was followed by the same events, as a second `drain` of
  `t/docs/IOLoop_Stream.py` and a third connection of `t/Pyjo/UserAgent.py`.
  `stop` of `_Loop` schedules a callback, which uvloop runs before that poll,
  and which halts the readers and the writers until the end of the run; a stop
  in a ready callback, as a timer of no time, does not halt the poll of its
  own iteration, which the loop of asyncio runs too, and which would starve
  the I/O of `one_tick` otherwise. The halt relies on a handle that is ready
  being ready in the next run still.
- libuv sets a handle that it watches to the non-blocking mode and never
  back, where the loop of asyncio leaves it. The mode belongs to the open file
  description, which a terminal shares with the shell, and
  `Pyjo.IOLoop.Stdio` reads and writes a terminal in the blocking mode, so
  `_Loop` sets a handle that was blocking back after `add_reader` and
  `add_writer`.
- On an error of a handle, as a pipe whose reader has closed it or a socket
  that the peer has reset, libuv of Linux stops watching it and calls its
  reader and its writer once, and uvloop closes its watcher but keeps it in
  its map of the handles, so the next `add_reader` or `add_writer` does
  nothing; the loop of asyncio calls them for as long as the error lasts. A
  writer of `Pyjo.IOLoop.Stdio` with nothing to write at that time never saw
  `EPIPE` again, and the halt after `stop` lost the one call. `_Loop` checks a
  handle for `POLLERR` with `poll` after its callback on Linux, and watches
  it again; macOS reports no such error, and its `poll`, at 6 µs, would cost
  more than an event.
- libuv counts a timer in whole milliseconds from `uv_now`, its clock rounded
  down, and uvloop rounds the delay to them, so a timer, as `asyncio.sleep`,
  was due up to a millisecond before its time by `time.monotonic`, where the
  loop of asyncio is never early, and the tests of Pyjoyment that measure a
  sleep with `time.monotonic`, as `t/Pyjo/Steps.py`, failed now and then.
  `call_later` of `_Loop`, which `call_at` of uvloop calls too, rounds the
  delay up to a millisecond and adds the one that the clock loses, as
  MagicStack/uvloop#755 does in uvloop, until it is released; a delay of no
  time stays a `call_soon` of uvloop.
- `Pyjo.Reactor._finalize` defers the cleanup of a finalizer that runs below a
  frame of a reactor or of its event loop, since pyjoyment/Pyjoyment#534,
  which takes the file of the module of the class of the reactor,
  `Pyjo/Reactor/Uvloop.py` with `_Loop`, wherever it is installed, and the
  modules of `event_loop_modules`. The reactor inherits
  `('asyncio', 'selectors')` and names no `uvloop`: the loop of uvloop is
  compiled with Cython and makes no frames of Python, and below the code that
  `uvloop.run` runs, the one place with frames of `uvloop/__init__.py`, is
  `asyncio/runners.py`. A probe of `_finalize` over the suite of Pyjoyment on
  the reactor found no frame of uvloop below any of its calls (#7).
- `PYJO_ASYNCIO_SLOW_CALLBACK` sets the `slow_callback_duration` of a loop of
  its own, as for `Pyjo.Reactor.Asyncio`, which the loop of uvloop has too.
- uvloop has wheels for CPython on Linux and macOS, not for PyPy or Windows, so
  the matrix of Tests has no PyPy, unlike the one of Pyjoyment.

## Development

The distribution depends on the release of Pyjoyment on PyPI, with the lowest
version that has what it uses, which `uv.lock` pins. A change of Pyjoyment that
is not released yet would be its Git repository in `[tool.uv.sources]` of
`pyproject.toml`, until its release, and not a path to the checkout next to
this one: uv applies the sources of a dependency of Git, so whoever installs
the reactor from Git would get a subdirectory of this repository that does not
exist. Before a release of the reactor, the source goes and the lowest version
of `dependencies` becomes the release of Pyjoyment that has the change, as a
wheel carries no sources of uv and would install the older release. That is
Pyjoyment 0.3.0 now, the first with the `_fork` of pyjoyment/Pyjoyment#497.
The tests lay the checkout next to this one over it with `--with-editable`,
so that they test what is there:

```sh
mise exec -- uv sync
mise exec -- uv run --with-editable ../Pyjoyment python -m Pyjo.Prove -l -r t
```

Perl's `prove` runs them too, with `.proverc`, under `uv run`, whose `python`
is the one of the environment, where Pyjoyment and the reactor are installed,
so that it needs no `PYTHONPATH`, unlike in Pyjoyment:

```sh
mise exec -- uv run --with-editable ../Pyjoyment prove -r t
```

The tests of Pyjoyment run on this reactor as well, with `PYJO_REACTOR`:

```sh
cd ../Pyjoyment
PYJO_REACTOR=Pyjo.Reactor.Uvloop mise exec -- uv run --project ../Pyjo-Reactor-Uvloop --with-editable . \
  python -m Pyjo.Prove -l -j 4 -r t
```

The workflow Tests runs the tests of the reactor against the release of
`uv.lock`, without `--with-editable`, so that a pull request tests what an
installation gets, and the suite of Pyjoyment of the tag of that release on
the reactor, or of its commit when `uv.lock` has it from Git. A dispatch with
`pyjoyment-ref`, a branch, a tag or a commit of Pyjoyment, installs its
Pyjoyment of Git over it with `uv run --with`, not editable, as an
installation from Git gets it, and runs the suite of its checkout, so that
what the next release of Pyjoyment breaks is known before the release.
It ends with the job `Tests`, the one check of it
that the ruleset of `main` requires, as in Pyjoyment: it fails when a job of
the matrix failed or was cancelled, so a new version of Python needs no change
of the ruleset.

Trunk checks the files with the linters of Pyjoyment, from `.trunk/trunk.yaml`:

```sh
trunk check --all
```

actionlint is the one of the maintained fork kjanat/actionlint, whose releases
continue those of rhysd/actionlint after 1.7.12, as in Pyjoyment: `downloads`
in `.trunk/trunk.yaml` replaces the URLs of the plugin with those of the fork,
whose files have the same names.

Biome formats and lints JSON, Markdown and YAML, with `biome.jsonc`, in the
place of prettier, markdownlint and yamlfmt, as in Pyjoyment, and yamllint
checks what Biome does not, as the duplicated keys. The version of Biome is
the pinned one of `.trunk/trunk.yaml`, where `!` keeps it from
`trunk upgrade`, and which Renovate bumps: the repository has no
`package.json` of its own. Renovate cannot run `biome migrate` nor
`biome format`, so the workflow Biome Migrate runs them with
`npx --yes @biomejs/biome@<version>` of that version, migrates `biome.jsonc`
and formats the files that the new version formats otherwise, which Trunk Check
would fail on, on the branch of Renovate, and commits them with the token of
the workflow, as the author that `gitIgnoredAuthors` of `.renovaterc.json`
names, so that Renovate keeps updating the branch, and starts the checks of the
commit with `workflow_dispatch`; anywhere else, a file that this Biome would
migrate or format fails the check. The token cannot change a workflow, so a
file of `.github/workflows` that the new Biome formats otherwise fails the push
of the commit, and is formatted by hand. The definition of
Biome in `.trunk/trunk.yaml` is the one of Pyjoyment, which explains why it is
not the one of the plugin of Trunk.

Its pyright needs the environment of `uv sync`, `.venv`, which `tool.pyright` of
`pyproject.toml` names, as the reactor imports Pyjoyment and uvloop, while
Pyjoyment has no dependencies to find; Trunk Check of CI runs `uv sync` first.
The examples and the tests, and `docs/conf.py`, are not checked by pyright: for them it takes the
regular package `Pyjo` of Pyjoyment, which hides `Pyjo.Reactor.Uvloop` of the
checkout.

The documentation is one page, `docs/index.rst`: the docstrings of the
module, which autodoc imports, and the examples from `examples/`, included,
never copied, as in Pyjoyment. Read the Docs installs it with `uv sync` of `uv.lock` and the
group `docs`, not with pip and a `docs/requirements.txt` as Pyjoyment does,
so that it builds with the versions of the lock, as the workflow Docs does.
The links to the modules of Pyjoyment come from intersphinx, to its stable
version from the stable one, and to latest from the others. The examples are
a rubric, not a section: they follow the docstring of the module, whose
sections are its own, so that a section would be a second title of the page.
The workflow Docs builds it with `-W`, as Read the Docs does, with the
Pyjoyment of `uv.lock`:

```sh
mise exec -- uv run --group docs --with-editable ../Pyjoyment sphinx-build -W --keep-going -b html docs docs/_build/html
```

`t/Reactor_Uvloop.py` is `t/Pyjo/Reactor_Asyncio.py` of Pyjoyment, the port of
`t/mojo/reactor_poll.t` of Mojolicious, in the subtests of 9.53, as
`t/Pyjo/Reactor_Poll.py` has them, with subtests of its own for the loop of
uvloop: a loop of its own, a given loop, a loop that is running, of asyncio
and of uvloop, a coroutine, `PYJO_ASYNCIO_SLOW_CALLBACK`, the child of a fork
and its exit, the wakeup fd of the signals, the finalizer of an async
generator in the debug mode, a stop in a callback of I/O, the blocking mode
of a handle, the writer of a pipe whose reader has closed it and a timer
that is not due before its time.
`t/docs/Reactor_Uvloop.py` runs the synopsis of the module, in both forms, as
`t/docs` of Pyjoyment does.

## Releases

The releases are those of Pyjoyment, with its workflows: a release is a tag of
the version of `pyproject.toml`, without a `v`, as `0.2.0`, which Automated
version sets with `uv version`, the components of its `--bump` from a list, as
`patch dev` or `minor rc`, or the version of `manual`, in the pull request of
the branch `automated/version`. After a release, a pre-release goes with the
release that it comes before, as PEP 440 orders `0.2.0.dev1` before `0.2.0`,
so `dev` alone after `0.2.0` fails. Automated tag tags the merge commit of
that pull request when it is merged, or with a comment `/tag` of a maintainer
on it, and starts Release on the tag. A development version, as `0.2.1.dev1`,
is not tagged. The version is static in `pyproject.toml`, as `uv version`
cannot set a dynamic one, and `__version__` of the module reads it from the
metadata of the distribution.

Each release has a milestone of GitHub named after its version, as `0.2.1`,
which holds the pull requests and the issues that go into it, so that the
milestone says what the diff and the notes of the release have. A pull
request that a maintainer or an agent opens gets the milestone of the next
release when it is opened, as `gh pr create --milestone 0.2.1`, and so does
the issue that it closes, as the change is then on its way into that
release. An issue alone waits for its triage without a milestone, and so
does a pull request of Renovate or of a workflow, as Automated version,
which none of them gives one. After a release, its milestone is closed, and
the milestone of the next release is named after the version of
`pyproject.toml` without its pre-release, as `0.2.1` of `0.2.1.dev1`, or the
next patch release while the version is still the one released, and is
renamed when a bump changes it.

Release builds the sdist and the wheel, attests their build provenance with
`actions/attest`, and makes a draft of the GitHub release with them, whose
notes are rewritten before it is published, and an SBOM in SPDX, attested
with them. The module bundles nothing, unlike the package of Pyjoyment, whose
SBOM lists the JavaScript libraries of its package, so the SBOM is what an
installation of the wheel gets: the distribution and its dependencies, as
Pyjoyment and uvloop, at the versions of `uv.lock`, installed in a virtual
environment of their own, which Syft scans. Syft on `uv.lock` itself would
take its dependency groups too, as Sphinx, which an installation does not get.
The sdist does not carry the SBOM, as the one of Pyjoyment does, as it is made
of the wheel, which is built after the sdist.

The workflow PyPI, run manually, publishes the files of the latest published
release, or of the release of the tag of its input, on PyPI once their
attestations of Release verify, in the environment `publishing`, which waits
for an approval and takes `main` and tags only. The trusted publisher of PyPI
names `pypi.yaml` and that environment.

```sh
gh attestation verify pyjo_reactor_uvloop-0.1.0.tar.gz -R pyjoyment/Pyjo-Reactor-Uvloop
```
