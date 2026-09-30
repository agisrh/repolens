# RepoLens

A command-line tool that turns a repository into technical documentation. Run one command and get **PDF**, **Word**, and **Markdown** documents covering the folder structure, the tech stack with exact versions, endpoints, database schema, configuration, and security findings. Every release can be exported as a documentation archive, including what changed since the previous release.

## Installation

Needs Python 3.10+ and `git`. Tested on macOS and Linux.

Install with [pipx](https://pipx.pypa.io), which keeps RepoLens in its own environment:

```bash
pipx install git+ssh://git@github.com/agisrh/repolens.git@v0.4.1
repolens --version
```

Update to the newest release at any time:

```bash
repolens update            # installs the newest vX.Y.Z tag
repolens update --check    # only reports whether one exists
```

For the optional AI summary, save your own Anthropic API key with `repolens auth login` (see [AI](#ai)).

### Shell completion

```bash
# zsh: add to ~/.zshrc
repolens completion zsh > ~/.repolens-completion.zsh && echo 'source ~/.repolens-completion.zsh' >> ~/.zshrc

# bash: add to ~/.bashrc
repolens completion bash > ~/.repolens-completion.bash && echo 'source ~/.repolens-completion.bash' >> ~/.bashrc

# fish
repolens completion fish > ~/.config/fish/completions/repolens.fish
```

Re-run the command after an update so new commands and options are completed too.

## Usage

Run `repolens` without arguments for the **interactive menu**: pick an action, the source (local folder or git URL), how to read the folder, a release to compare with, formats, AI, and language. Before running, the menu prints the equivalent command so it can be reused in scripts or CI.

```bash
# Scan a local folder (follows .gitignore) and export PDF + Word + Markdown
repolens scan ../my-app

# Scan a local folder as it is on disk, without git: every file (including git-ignored ones), no commit/tag info
repolens scan ../my-app --no-git

# Documents in Indonesian (default: English, or REPOLENS_LANG)
repolens scan ../my-app --lang id

# Show the summary and findings without writing files or calling AI
repolens scan ../my-app --dry-run

# Scan a release tag. Your working tree is not touched (the repo is cloned to a temporary folder).
repolens scan ../my-app --ref v3.2.0

# Release document + changes since the previous release
repolens scan ../my-app --ref v3.2.0 --compare-ref v3.1.3

# Straight from a git URL
repolens scan git@github.com:my-org/my-app.git --ref v3.2.0

# Only some formats, without AI
repolens scan ../backend-api --format pdf,docx --no-ai

# In CI: exit code 1 when a section is probably incomplete
repolens scan . --ref "$TAG" --compare-ref "$PREV_TAG" --no-ai --strict

# Render again from a previous scan, without scanning
repolens export docs-output/my-app-v3.2.0/scan.json --format docx

# Compare two scans
repolens diff docs-output/my-app-v1.0.0/scan.json docs-output/my-app-v1.1.0/scan.json

# Machine-readable output: JSON on stdout (scan, doctor, diff, auth status)
repolens doctor ../my-app --json | jq '.coverage[] | select(.level == "warn")'
```

### Language

The terminal and the documents (PDF, Word, Markdown, including the AI narrative) are in English by default. Choose Indonesian with `--lang id`, or set `REPOLENS_LANG=id` for every command. `repolens export` uses the language of the scan unless `--lang` is given. Findings and notes produced during a scan stay in that scan's language, so scan again for a full translation. Older `scan.json` files (version 0.1, written in Indonesian) can still be exported and compared.

### Local folders: with or without git

| Mode | Command | Files read | Release info |
| :--- | :--- | :--- | :--- |
| Working tree (default) | `repolens scan <folder>` | Files on disk that are not git-ignored | Commit, branch, tag, remote |
| Plain folder | `repolens scan <folder> --no-git` | Every file on disk, except dependency/build folders (`node_modules`, `vendor`, `build`, ...) and `ignore` in `.repolens.yml` | None |
| A release | `repolens scan <folder> --ref v1.2.0` | The content of that commit (cloned to a temporary folder) | Full |

A folder that is not a git repository is scanned as a plain folder automatically. `--no-git` cannot be combined with `--ref`, `--compare-ref`, or a git URL.

Output goes to `docs-output/<project>-<release>/`:

```text
docs-output/my-app-v3.2.0/
├── my-app-v3.2.0.pdf
├── my-app-v3.2.0.docx
├── my-app-v3.2.0.md
└── scan.json          # raw scan data, used to export again and to compare releases
```

If the output folder already holds documents of **another project** with the same name and release (for example two forks with the same `name` and `version` in `pubspec.yaml`), the scan stops instead of overwriting them, and tells you how to tell the two apart: a `name` in `.repolens.yml`, another `--out`, or `--force`. Scanning the same project again replaces its previous result.

### Exit codes

| Code | Meaning |
| :--- | :--- |
| 0 | Success |
| 1 | Failed (bad input, git error, file not found), or something needs attention with `--strict` |
| 2 | Invalid arguments, or an unexpected error. Run again with `--debug` (or `REPOLENS_DEBUG=1`) for the traceback |
| 130 | Cancelled (Ctrl+C) |

Git never asks for a username or password interactively, so it cannot hang in CI. Set up access with an SSH key or a credential helper. Tokens in URLs are never shown in error messages or documents.

## Projects with an unusual layout

Every project has its own quirks: `vendor/` not committed, routes in extra files, tables without migrations, and so on. Three tools deal with them.

### 1. `repolens doctor`: check before generating documents

```bash
repolens doctor ../my-app
```

It shows what was detected and where it came from, then what is **probably missing** and how to fill it in. For example:

```text
Coverage
  ⚠ [Tech stack] CodeIgniter 4 version unknown (spark + app/Config/Routes.php (exact version unknown: no vendor/ folder)).
    → Set `frameworks: [{name: CodeIgniter 4, version: ...}]` in `.repolens.yml`, or run `composer install` before scanning.
  ⚠ [Endpoint] 2 of 12 controllers do not appear in any route: Legacy, Report.
    → They may be reached through auto-routing or dynamically built routes. Add their endpoints under `endpoints` in `.repolens.yml`, ...
```

The same findings are printed after `scan` and appear in the **Scan Coverage** section of the document. Add `--strict` to exit with code 1 when there are findings (useful in CI).

### 2. `.repolens.yml`: what cannot be detected

```bash
repolens init ../my-app     # create a template from what was detected
```

The file lives in the project root and is committed, so it applies to every release.

```yaml
name: My App
version: 2.1.0                       # when no manifest records a version
frameworks:
  - {name: CodeIgniter 4, version: 4.1.3}
routes:                              # route files outside the standard locations
  - app/Config/RoutesAdmin.php
schema:                              # schema-only SQL dump, any extension, may be git-ignored
  - database/schema.sql
ignore:                              # excluded from the scan
  - public/assets/vendor
endpoints:                           # dynamic endpoints that cannot be detected
  - {method: GET, path: /legacy/export, handler: Legacy::export, note: auto-routing}
notes:                               # shown in the document
  - Auto-routing is enabled in production.
tree_depth: 4
```

`doctor` reports unknown keys and file patterns that match nothing. A `.docgen.yml` from before the rename to RepoLens is still read; `doctor` suggests renaming it.

### 3. Regression tests: fixes that do not break each other

```bash
pip install -e ".[dev]"
pytest                 # synthetic fixtures, fast, no network
pytest -m corpus       # real repositories pinned to a commit (tests/corpus.yml)
```

When a project comes out wrong:

1. Add a small fixture under `tests/fixtures/<name>/` that mimics the pattern, and a test in `tests/test_fixtures.py`.
2. If the repository is reachable, also add it to `tests/corpus.yml` with the tested commit and hand-checked results.
3. Fix the extractor until every test passes, not only the new one.

CI runs the tests on Python 3.10–3.14 on Linux and macOS for every push and pull request.

How the code is organised, its conventions, and where to add a new stack, section, or command: [CONTRIBUTING.md](CONTRIBUTING.md).

## What the document contains

| Section | Source |
| :--- | :--- |
| Summary, architecture, modules | AI (optional), based on the scan facts |
| Changes since the previous release | `--compare-ref` or `--compare` |
| Release information | git: commit, tag, branch, remote (credentials in URLs are removed) |
| Tech stack & versions | Manifests + lock files (the versions actually installed) |
| Folder structure | File tree, following `.gitignore` |
| Endpoints & routes | Server route definitions, client API calls, UI routes |
| Database | SQL, migrations, ORM entities/models, connection settings |
| Configuration | **Names** of env and config keys (values are never read) |
| Scan coverage | What is probably missing, and how to fill it in |
| Platforms & infrastructure | Android/iOS, Dockerfile, docker-compose, CI/CD |
| Dependencies | Every package per manifest: declared vs installed |
| Security | Token/password/private-key patterns, committed env files. Levels *high*, *medium*, *low* (test files and client Firebase config keys) |

## Supported stacks

| Stack | Endpoints | Database | Versions |
| :--- | :--- | :--- | :--- |
| Spring Boot (Java/Kotlin) | `@*Mapping` + class `@RequestMapping` prefix | JPA `@Entity`, SQL | Maven, Gradle |
| Laravel | `routes/*.php` including `prefix`/`group`, `resource`, `apiResource` | Migrations | `composer.lock` |
| CodeIgniter 4 | `app/Config/Routes.php` including `group`, `resource` | Migrations, Models (`$table`, query builder) | composer, `system/CodeIgniter.php` |
| CodeIgniter 3 | `application/config/routes.php` | SQL, Models (query builder) | `system/core/CodeIgniter.php` |
| Next.js | App Router `route.ts`, Pages API, pages | Prisma, Drizzle, TypeORM | npm/yarn/pnpm lock |
| React | React Router, `axios`/`fetch` calls | - | npm/yarn/pnpm lock |
| Express / NestJS | `app.get(...)`, `@Controller` + `@Get` | Prisma, TypeORM, Sequelize (engine) | npm lock |
| Flutter / Dart | API calls in data sources (Dio, http, `.call` wrappers) | Hive | `pubspec.lock`, `.fvmrc` |
| Python (FastAPI, Flask, Django) | Route decorators, `urls.py` | Django models | requirements, pyproject |
| Go (Gin, Echo, Fiber) | `r.GET(...)` | - | `go.mod` |

For other stacks, the general sections (folder structure, languages, dependencies, env, security, git, CI/Docker) are still filled in.

## AI

Unless `--no-ai` is given, RepoLens asks Claude to write a summary, an architecture overview, folder descriptions, a module list, setup steps, and observations. Without an API key the AI part is skipped and the documents are still generated.

### Your own API key and model

Each user brings their own Anthropic API key:

```bash
repolens auth login                  # asks for the key (hidden input) and a model, checks it with Anthropic, then saves it
repolens auth status                 # key in use (masked: sk-ant-…a1b2), where it comes from, the model, and a check
repolens auth logout                 # removes the saved key

pass show anthropic | repolens auth login --model claude-sonnet-5-5   # non-interactive: the key is read from stdin
```

The menu has the same options (*Set up AI*), and offers to set a key when you choose the AI summary without one.

- **Storage:** the OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service). When none is available (a headless server, or `REPOLENS_NO_KEYRING=1`), the key goes to `~/.config/repolens/credentials.json` with mode `600`.
- **Key order:** `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` → the key from `repolens auth login` → an `ant auth login` profile. CI keeps using environment variables as usual.
- The key is **never** accepted as a flag (it would show up in shell history and `ps`), written to `.repolens.yml` (which is committed), or shown in full.
- The key is checked with Anthropic before it is saved (Models API, no token cost). A rejected key is not saved.
- **Model:** `--model` → `REPOLENS_MODEL` → the model chosen at `auth login` → default `claude-opus-5-5`. `auth login` offers `claude-opus-5-5` (most thorough) and `claude-sonnet-5-5` (faster, about half the cost). The settings folder can be moved with `REPOLENS_CONFIG_DIR`.

Only **scan facts** are sent to the AI: names, versions, paths, column names, env key names, and a README excerpt. Source code, env values, and secret snippets are never sent. Use `--no-ai` when no data may leave the machine at all.

Requests use server-side fallback (`fallbacks: "default"`) in case a request is declined by a safety classifier.

## Environment variables

| Variable | Purpose |
| :--- | :--- |
| `REPOLENS_LANG` | Output language, `en` or `id` |
| `REPOLENS_MODEL` | Claude model for the AI summary |
| `REPOLENS_DEBUG` | Show full tracebacks on unexpected errors |
| `REPOLENS_CONFIG_DIR` | Where settings and the fallback credentials file live |
| `REPOLENS_NO_KEYRING` | Store the API key in a file instead of the OS keychain |
| `REPOLENS_REPO` | Repository `repolens update` installs from (default `git@github.com:agisrh/repolens.git`) |
| `ANTHROPIC_API_KEY` | API key; takes priority over the saved one |

The names from before the rename (`DOCGEN_LANG`, `DOCGEN_DEBUG`) still work.

## Limitations

- Static analysis: code is never run. Routes built at runtime (auto-routing, routes from a database, dynamically assembled prefixes) may be missed. The document says so when it notices.
- The security scan looks at the current files only, not the git history.
- PDF fonts use Arial Unicode/Menlo (macOS) or DejaVu (Linux). Without them, special characters are replaced by ASCII equivalents.
- Windows is not tested yet.

## License

[MIT](LICENSE)
