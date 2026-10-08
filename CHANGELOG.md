# Changelog

Notable changes per release. This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for its own interface;
compatibility with application versions is tracked separately in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

## [Unreleased]

Nothing yet.

## [0.1.0-alpha] — 2026-10-08

First public release. Tagged `v0.1.0-alpha`. The version has a single source of
truth — the `__version__` attribute in `src/claude_zh_patch/__init__.py`, which
`pyproject.toml` reads via `dynamic = ["version"]` — so the tag, the version
command and the install marker all report the same identifier. Packaging tools
normalise it to the PEP 440 form `0.1.0a0`.

It is a pre-release: the core paths work and are tested, but only one application
build has been verified, on one machine.

### Added

- **Install pipeline.** `check`, `apply`, `verify` and `rollback` commands.
  The source application is only ever read; output goes to a separate bundle that
  must not already exist, and a partially created copy is removed on failure.
- **Corrected ad-hoc signing.** Editing a bundle invalidates its signature, so the
  copy is re-signed ad-hoc, inside-out: nested code first, enclosing bundle last.
  Restricted entitlements (`com.apple.application-identifier`,
  `com.apple.developer.*`, `keychain-access-groups`) are removed, because an
  ad-hoc signature cannot substantiate a team identity or a provisioning profile.
  `com.apple.security.cs.disable-library-validation` is added, which an ad-hoc
  signed Electron bundle needs in order to load its own frameworks.
- **Hard version gate.** Only builds in `SUPPORTED_VERSIONS` are installable, with
  no override flag. Unsupported versions exit with code 3 and explain the
  alternative. Builds that were inspected but not run are recorded separately and
  stay non-installable.
- **Structural verification.** Every rewrite site must occur exactly the expected
  number of times; a whole-tree scan rejects an allowlist sequence found outside a
  known site; and each rewritten file's sha256 is compared against the digest
  recorded for that version.
- **Language resource handling.** `--catalog-dir` takes a user-prepared resource.
  The project ships none, and contains no extraction or download logic. A JSON
  Schema, a blank template, a manifest format, ICU MessageFormat validation, and
  format-argument comparison against the application's own messages.
- **Format arguments judged by structure, not by substring.** Both messages are
  parsed and each argument is recorded with the chain of `(selector, label)` pairs
  it sits under. An argument is excused only when every place the application uses
  it is beneath a branch the translation removed — a language choosing not to
  inflect. An argument the application renders outside every branch, or inside a
  branch that was kept, is refused. Accepted collapses need no flag and are listed
  by `lint` and counted in the install marker.
- **No override for format arguments.** There is no flag that lets a visible
  difference through, and no default warn-only mode. Both refusals are asserted by
  the test suite.
- **`lint` command.** Reports every problem in a language resource, in detail:
  per-message reason, the application's format arguments, the supplied format
  arguments, what is missing, and what was accepted as a branch collapse.
  `--report PATH` writes the same detail to a file. Unlike `apply`, `lint` never
  downgrades a finding, so it is the command to run while fixing a resource.
- **`keys` command.** Lists the message keys the application expects with empty
  values, so a resource can be built without exporting the application's English
  text.
- **Security scanner.** `scan` checks for credentials, personal data and
  third-party material. Findings never echo the matched value. The test suite
  asserts the repository itself scans clean.
- **Test suite.** 195 standard-library tests covering the version gate, the
  signing rules, ICU validation, catalog validation, the install pipeline,
  verification, rollback, the CLI surface and the documentation.
- **Documentation.** English and Simplified Chinese guides, a compatibility
  matrix, a troubleshooting guide, a security policy, and a disclaimer naming the
  verified environment and every limitation found in it.

### Known limitations

- Verified on a single configuration: macOS 26.5.2 on Apple Silicon, with
  **System Integrity Protection disabled** and a locally created, non-quarantined
  copy. `spctl` reports the resulting copy as rejected.
- Only Claude Desktop `2.26454.0` is installable.
- The copy does not carry the original's team-scoped keychain access groups, so
  keychain-backed behaviour differs. Native integrations are untested.
- A message that renders an argument the application does not provide, or that
  loses an argument the application renders outside every branch, is refused with
  no way to override. A message that removes a plural/select branch is accepted
  automatically and counted in the install marker.

### Fixed

Relative to the earlier prototype this tool replaces:

- `codesign --preserve-metadata=entitlements` was carrying Anthropic's restricted
  identity entitlements onto an ad-hoc signature. They are now stripped, and the
  resulting entitlement set is asserted by tests against the set observed on a
  working installation.
- The prototype required the two allowlist occurrences to live in two different
  files. This build has both in one file, so a correct installation was refused.
  The anchor is now described per file with an exact count, and the whole-tree
  total is checked separately.
- Failures left a partially created copy behind. They are now cleaned up.

[Unreleased]: https://github.com/kahomesl/claude-desktop-3p-zh-hans-patch/compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/kahomesl/claude-desktop-3p-zh-hans-patch/releases/tag/v0.1.0-alpha
