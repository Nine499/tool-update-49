# AGENTS.md

## What this is

`tool-update-49` is a Python CLI that concurrently updates command-line tools published as
GitHub releases. For each tool in a YAML manifest it resolves the latest release tag,
downloads the asset (HTTP Range probe, up to 5 parallel segments), extracts only the
whitelisted archive members, and atomically installs them into `~/.local/bin`.

It is not a package manager: there is no version pinning, no rollback, and the install
directory is fixed.

## Stack & Run

- Python >= 3.12, dependencies managed with `uv`; `uv.lock` is committed.
- Build backend: hatchling. Entry point: `tool-update-49 = tool_update_49.cli:main`.
- Runtime deps: `httpx[http2]`, `pyyaml`, `rich`. Dev dep: `pytest`.
- ruff config lives in `pyproject.toml`: target `py312`, line length 88,
  rules `E, F, I, UP, B, SIM`.

```bash
uv sync
ruff check src tests
ruff format --check src tests
uv run pytest
uv build
uv run tool-update-49 --help
```

## Layout

```text
src/tool_update_49/
  cli.py        argparse entry, config loading, exit codes
  config.py     manifest parsing and validation
  net.py        GitHub token, latest release lookup, HTTP retry helper
  download.py   Range probe, segment planning, parallel download
  archive.py    selective zip / tar member extraction
  install.py    atomic install into the bin directory
  ui.py         Reporter protocol, rich live panel, plain line logger
  updater.py    per-tool pipeline and concurrency semaphore
  errors.py     UpdateError / RetryableError / ConfigError helpers
  __main__.py   `python -m tool_update_49`
tests/          pytest suites, one file per module
```

## Conventions

- Async I/O only, through one shared `httpx.AsyncClient` created in `updater.run_updates`.
- Raise `UpdateError` for expected user-facing failures. Raise `RetryableError` (a
  subclass) for transient ones; `download` retries those up to `MAX_ATTEMPTS` (3) with
  exponential backoff.
- Core modules never print. All output goes through the `Reporter` protocol in `ui.py`.
  When adding an event, update the protocol and both `RichReporter` and `PlainReporter`.
- User-facing error messages, comments, and docstrings are Simplified Chinese.
- Type hints everywhere; every module starts with `from __future__ import annotations`.
- Immutable dataclasses use `frozen=True, slots=True` (see `Tool`, `Segment`).
- One function does one thing; prefer early returns over nesting.

## Tasks

**Add a tool.** No code change. Edit `$SECRETS49/tool-update-49.yaml` and add an entry
with `name`, `repo`, `url`, `files`.

**Add or change a manifest field.** Extend `FIELDS` and `_parse_tool` in `config.py`, add
rejection cases to `tests/test_config.py`, and update the README field table.

**Tune downloads.** Constants are in `download.py`: `SEGMENTS` (max segments),
`MIN_SEGMENT_SIZE` (1 MiB), `MIN_SEGMENTED_SIZE` (2 MiB threshold), `CHUNK_SIZE`.

**Tune concurrency.** `updater.CONCURRENCY` sets how many tools run at once. The HTTP pool
is sized `CONCURRENCY * SEGMENTS` in `run_updates`.

**Add a UI event.** Add it to the `Reporter` protocol, implement it in both reporters, then
call it from `updater.py`.

**Bump the version.** Use the `time-version-49` skill to generate `YYYYMMDD.HHMM.SSMS`,
then update both `pyproject.toml` `[project].version` and
`src/tool_update_49/__init__.py` `__version__`.

## Traps

- The secrets-directory env var is `SECRETS49`. The manifest must be at
  `$SECRETS49/tool-update-49.yaml`.
- The token key inside `$SECRETS49/.env` is `github-no-403`; the fallback is
  `GITHUB_TOKEN`. The token is attached only to `api.github.com` requests.
- `files` keys are archive member basenames, matched case-insensitively. They are not
  install names.
- For non-archive URLs, `files` must have exactly one entry, and its key must equal the
  URL filename (case-insensitive).
- Install names are global across tools and must be safe: no `/`, `\`, or NUL, and not
  exactly `.` or `..`.
- Version must be generated with the `time-version-49` skill and kept identical in two
  files. Never hand-write, increment, or reuse it.
- Never run `uv tool install`; the user installs manually with `uv tool install --force .`.
- Do not commit or push unless explicitly asked.
- The CLI takes no options except `-h` / `--help`; argparse uses `add_help=False` with an
  explicit help action.
- Output goes to stderr. `RichReporter` is used only when stderr is a TTY; otherwise
  `PlainReporter` prints one line at a time.
- The install directory is hard-coded to `~/.local/bin` in `cli.default_bin_dir`; there is
  no override.
