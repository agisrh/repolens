# Contributing to RepoLens

This guide explains how the code is organised, the conventions it follows, and where to
make the most common changes. Every module starts with a docstring that explains what it
does; read those for the details.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                          # fast tests, no network
.venv/bin/ruff format repolens tests      # format the code
.venv/bin/ruff check repolens tests       # lint: line length, imports, likely bugs
```

CI runs the same `ruff` checks and the tests on Python 3.10–3.14 (Linux and macOS) for
every push and pull request.

## How a scan flows through the code

```
repolens scan ../app
   │
   ├─ cli.py                  parses arguments, turns errors into exit codes
   ├─ commands/scan.py        the steps of the command, and what it prints
   │
   ├─ scanner.py              clones the source if needed, then runs every extractor
   │    ├─ repo.py            lists and reads the files (follows .gitignore)
   │    ├─ projectconfig.py   reads .repolens.yml
   │    ├─ extractors/        one package or module per kind of fact (see below)
   │    └─ coverage.py        findings: what is probably missing, and how to fix it
   │
   ├─ ai.py                   optional narrative from Claude (credentials.py: the API key)
   ├─ diff.py                 changes between two scans
   │
   └─ output.py               writes scan.json and the documents
        ├─ document/          facts -> a list of format-neutral blocks, one module per section
        └─ render/            blocks -> Markdown, Word, PDF
```

The **scan facts** (the dict that `scanner.scan()` returns and `scan.json` stores) are the
only thing passed between these layers. Extractors never format text for the document, and
the document never reads files.

## Code layout

| Path | What lives there |
| :--- | :--- |
| `repolens/cli.py` | Entry point: builds the parser from `commands/` and handles errors |
| `repolens/commands/` | One module per command: `NAME`, `register()`, `run()` |
| `repolens/menu.py` | The interactive menu; it only builds the argument list of a command |
| `repolens/ui.py` | Terminal output: headers, step markers, spinners, summaries |
| `repolens/i18n.py` | `t(english, indonesian)` and language-neutral labels |
| `repolens/scanner.py` | Preparing the source and running every extractor |
| `repolens/extractors/endpoints/` | Routes and API calls, one module per stack |
| `repolens/extractors/database/` | Schema readers (SQL, migrations, ORM, PHP) and engines |
| `repolens/extractors/deps/` | Dependency manifests and lock files, one module per ecosystem |
| `repolens/extractors/stack.py` | Frameworks and runtimes (`FRAMEWORK_RULES`) |
| `repolens/extractors/platforms.py` | Android/iOS settings, Docker, Compose, CI |
| `repolens/extractors/config.py` | Env keys and secret detection |
| `repolens/extractors/overview.py` | Project identity, git info, folder tree, languages |
| `repolens/extractors/_text.py` | Text helpers shared by the extractors (brackets, strings, comments) |
| `repolens/document/` | One function per document section; `SECTIONS` sets the order |
| `repolens/render/` | Renderers: `markdown.py`, `docx_out.py`, `pdf_out.py` |

## Conventions

- **Line length is 100 characters**, and `ruff format` decides the layout. Do not align code
  by hand; run the formatter.
- **Every module starts with a docstring** that says what it is for. Functions that are not
  obvious from their name get a one-line docstring (more when there is a *why* to explain).
  Comments explain *why*, not *what*.
- **Keep functions small**: one step, one area, or one kind of input each. A function that
  needs section comments inside it should usually be several functions.
- **Every text a user can see is bilingual**, written side by side where it is used:
  `t("English text", "Teks bahasa Indonesia")`. Never hard-code one language. Long texts
  are split into adjacent string literals, which Python joins.
- **Values stored in scan.json that code compares against** (severity, change kind) are
  language-neutral codes; `i18n.label()` turns them into display text.
- **Errors the user can fix** are raised as `RuntimeError` or `OSError` with a readable
  message; `cli.main()` prints it without a traceback. Anything else is treated as a bug.
- **Never read or send secret values.** Env files contribute key names only, secrets are
  masked, and the AI receives scan facts, never file contents.
- **Scanning must not fail on odd input**: extractors skip what they cannot parse, and
  `.repolens.yml` problems become warnings.

## Adding things

| To add | Do this |
| :--- | :--- |
| A command | A module in `repolens/commands/` with `NAME`, `register(subparsers, common)`, `run(args)`, added to `COMMANDS` in `commands/__init__.py`. `--help` and shell completion follow automatically; to offer it in the interactive menu, add a flow to `FLOWS` in `menu.py`. |
| A framework recognised from its package | A row in `FRAMEWORK_RULES` in `extractors/stack.py`. |
| Routes of a new stack | A function `(repo) -> list[dict]` in `extractors/endpoints/` using `FileScan`, called from `extract()` in `endpoints/__init__.py`. |
| A schema source | A reader `(repo) -> list[dict]` in `extractors/database/` using `table()` / `column()`, called from `extract()` in `database/__init__.py`. |
| A dependency manifest | A reader `(repo, path) -> dict` in `extractors/deps/`, listed in `READERS` in `deps/__init__.py`. |
| A coverage check | A function `(repo, facts) -> list[dict]` in `coverage.py`, added to `CHECKS`. |
| A document section | A function `(doc, facts)` in `repolens/document/`, added to `SECTIONS`. Use the `Blocks` methods (`doc.h1`, `doc.table`, ...). |
| An output format | A `render(blocks, path) -> Path` in `repolens/render/`, added to `RENDERERS` in `output.py`. |
| A `.repolens.yml` key | `KNOWN_KEYS` and a validator in `VALIDATORS` in `projectconfig.py`, then use it in `scanner.py` or `apply_overrides()`. |

Every new extractor or fix comes with a test: a small fixture in `tests/fixtures/` and a
test in `tests/test_fixtures.py`, or a focused test in `tests/test_extractors.py`. When a
real repository is available, add it to `tests/corpus.yml` too (`pytest -m corpus`).

## Tests

| File | Covers |
| :--- | :--- |
| `tests/test_fixtures.py` | Scanning synthetic projects per stack, and the rendered documents |
| `tests/test_extractors.py` | Single extractors, for cases the fixtures do not cover |
| `tests/test_cli.py` | Commands, validation, error messages, git sources |
| `tests/test_menu.py` | The interactive menu, driven with scripted answers |
| `tests/test_auth.py` | API key storage and `repolens auth` |
| `tests/test_ai.py` | The AI request and every way it can be skipped (fake client) |
| `tests/test_update_completion.py` | `repolens update` and shell completion |
| `tests/test_corpus.py` | Real repositories pinned to a commit (`pytest -m corpus`) |

Tests never touch the real keychain, config folder, API key, or network (see
`tests/conftest.py`).
