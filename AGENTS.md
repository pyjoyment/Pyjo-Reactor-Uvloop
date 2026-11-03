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
  of asyncio, which overrides only `_own_loop`, the loop that the reactor makes
  for itself: `uvloop.new_event_loop()` in the place of
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
- The child of a fork, as a worker of `Pyjo.Server.Prefork`, moves to a new
  loop of its own, which `_fork` of `Pyjo.Reactor.Asyncio` makes with
  `_own_loop`, so of uvloop, as libuv of the parent is not the child's.
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
exist. The tests lay the checkout next to this one over it with
`--with-editable`, so that they test what is there:

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
the reactor. A dispatch with `pyjoyment-ref` lays a checkout of the ref over
it, as in development, so that what the next release of Pyjoyment breaks is
known before the release. It ends with the job `Tests`, the one check of it
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
`package.json` of its own. Renovate cannot run `biome migrate`, so the
workflow Biome Migrate runs it with `npx --yes @biomejs/biome@<version>` of
that version, migrates `biome.jsonc` on the branch of Renovate and commits it
with the token of the workflow, as the author that `gitIgnoredAuthors` of
`.renovaterc.json` names, so that Renovate keeps updating the branch, and
starts the checks of the commit with `workflow_dispatch`; anywhere else, a
`biome.jsonc` that this Biome would migrate fails the check. The definition of
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
and of uvloop, a coroutine, `PYJO_ASYNCIO_SLOW_CALLBACK` and the child of a
fork.
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
gh attestation verify pyjo_reactor_uvloop-0.2.0.tar.gz -R pyjoyment/Pyjo-Reactor-Uvloop
```
