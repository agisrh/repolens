# Changelog

All notable changes to RepoLens. Versions follow [Semantic Versioning](https://semver.org); releases are git tags (`vX.Y.Z`).

## [0.4.0] - 2026-09-30

### Added
- `repolens update` installs the newest release tag (pipx or pip); `--check` only reports it. Also in the menu.
- `repolens completion bash|zsh|fish` prints a shell completion script generated from the command definitions.
- Logo in the interactive menu.
- CI on GitHub Actions: tests on Python 3.10–3.14 on Linux and macOS, plus a package build check.
- MIT license, package metadata, and this changelog.

### Changed
- README rewritten in English, with installation through pipx.
- A scan that would overwrite another project's documents now explains which two projects clash, where the shared name comes from, and the exact fixes.
- `scan` and `doctor` report a missing folder before printing anything else.
- `doctor` listings no longer end in trailing spaces.

## [0.3.0] - 2026-09-30

### Added
- `repolens auth login | status | logout`: each user saves their own Anthropic API key (OS keychain, or a 0600 file when there is none) and default model. The key is checked with the Models API before it is saved.
- The scan menu offers to set up a key when the AI summary is chosen without one.

### Changed
- Default model is `claude-opus-5-5`.
- Model order: `--model`, `REPOLENS_MODEL`, the model chosen at login, then the default.

## [0.2.0] - 2026-09-30

### Changed
- Renamed from kalog-docgen (`docgen`) to RepoLens (`repolens`). Old names are still read: `.docgen.yml`, `DOCGEN_LANG` / `DOCGEN_DEBUG`, and `scan.json` files with `docgen_version`.

### Added
- English output by default, `--lang id` for Indonesian.
- Interactive menu when run without arguments; `--no-git`, `--dry-run`, `--json`, `--debug`.

## [0.1.0]

- First version: `scan`, `doctor`, `init`, `export`, `diff`; PDF, Word, and Markdown output.

[0.4.0]: https://github.com/agisrh/repolens/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/agisrh/repolens/releases/tag/v0.3.0
