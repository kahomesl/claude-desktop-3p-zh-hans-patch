# Contributing

Thanks for considering it. This is a small project with a deliberately narrow
scope, and the most useful contributions are usually small ones.

## The rules that matter

**Do not submit third-party material.** No application binaries, no modified
application assets, no extracted message catalogs, no provisioning profiles, no
signing material. If a change requires one of those to demonstrate, describe it
instead.

**Do not submit a language resource.** This repository ships no translation data
and will not start. Community translations belong in their own repository — see
[the translation section](#translations).

**Do not bypass the version gate.** There is no override flag by design.
"Add `--force`" will be closed.

## Getting set up

```bash
git clone https://github.com/kahomesl/claude-desktop-3p-zh-hans-patch.git
cd claude-desktop-3p-zh-hans-patch
./zh-patch version
```

Python 3.9 or newer, standard library only. No dependencies to install, no
virtual environment required.

## Before you open a pull request

```bash
python3 -m unittest discover -s tests -t .   # everything
./zh-patch scan .                            # the repository's own scanner
```

Both must be clean. The test suite includes a check that the repository scans
clean, so a stray secret fails the suite as well as the scanner.

To run one module while you work:

```bash
python3 -m unittest tests.test_signing -v
```

## Layout

| Path | Contents |
| --- | --- |
| `src/claude_zh_patch/compat.py` | Version allowlist, anchors, digests — the safety-critical table |
| `src/claude_zh_patch/signing.py` | Entitlement stripping and ad-hoc re-signing |
| `src/claude_zh_patch/patcher.py` | Plan construction and the apply pipeline |
| `src/claude_zh_patch/catalog.py` | Language resource loading and validation |
| `src/claude_zh_patch/icu.py` | ICU MessageFormat validator |
| `src/claude_zh_patch/lifecycle.py` | Verification and rollback |
| `src/claude_zh_patch/security_scan.py` | The scanner |
| `src/claude_zh_patch/cli.py` | Command line surface and exit codes |
| `tests/support.py` | Synthetic fixtures; every fixture is constructed, none embedded |

## Changing the signing code

This is the part with the least room for error, and the tests pin it hard: the
resulting entitlement set is asserted against the exact set observed on a working
installation. If you change `strip_restricted` or `plan_main_entitlements`, expect
`tests/test_signing.py` to fail and read why before adjusting the expectation.

Two things to keep:

- restricted entitlements stay out — an ad-hoc signature cannot substantiate a
  team identity, and carrying them produces a bundle that claims something it
  cannot prove;
- signing order stays inside-out. Apple deprecates `--deep` for signing precisely
  because it applies one set of options to every nested item.

## Adding support for an application version

Follow every step in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md#adding-support-for-a-new-version).
The pull request should contain the new `VersionInfo` entry, the recorded
digests, and — in the description — the environment you tested on, including
whether SIP was enabled. A version that has only been inspected goes in
`ANCHOR_ONLY_VERSIONS`, not `SUPPORTED_VERSIONS`.

## Translations

A community translation may be contributed, under these conditions:

- **independent creation** — written by a contributor, or from a source whose
  licence permits redistribution;
- **licence declared** — the contribution states a licence that permits
  redistribution and modification;
- **reviewed** — a maintainer checks the declaration before it is published;
- **attribution kept**.

Copying text out of the application or out of a web interface and submitting it
will be rejected, however good the translation is. Publishing falls to a
maintainer decision, and a translation will not be merged into this repository —
this repository holds tooling only.

## Tests

Fixtures are synthetic and built at run time in `tests/support.py`. When you need
a secret in a test, build it by concatenation:

```python
secret = "sk-ant-" + "A" * 28
```

so that the literal never appears in the repository and the scanner does not
report the test suite for its own fixtures.

Test names should say what the behaviour is, not which function is exercised:
`test_dropped_format_argument_blocks_the_install`, not `test_findings_for`.

## Documentation

User-facing behaviour changes belong in the documentation as well as the code:
`README.md` and `README.zh-Hans.md` for anything a user sees, the relevant file
under `docs/`, and an entry under `## [Unreleased]` in `CHANGELOG.md`.

The English and Simplified Chinese documents are kept in step. If you change one,
change both, or say in the pull request that the other is outstanding.

Required disclosures — the unofficial status, the absence of translation data,
the SIP/Gatekeeper/ad-hoc consequences — are asserted by `tests/test_docs.py`.
Delete a disclosure and the suite fails, which is the intent.

## Commit messages and pull requests

Explain *why* in the message. A commit that says what changed but not why is hard
to review and harder to revert.

Use the pull request description for context: what you observed, what you tried,
what you ruled out.

## Reporting a bug

Use [the troubleshooting guide](docs/TROUBLESHOOTING.md#reporting-a-problem) to
collect the right information. Please do not attach your language resource, a
copy of the application, or anything containing credentials or chat content.

## Licence

Contributions are accepted under the Apache License 2.0, covering original work
only, as described in [`NOTICE`](NOTICE).
