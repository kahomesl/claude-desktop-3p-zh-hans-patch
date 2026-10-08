# Official Claude Desktop 2.26454.2 — validation record

**Status: runtime tested on one macOS environment and now included in the
strict version allowlist on this adaptation branch.** See
[COMPATIBILITY.md](COMPATIBILITY.md) for the definitive evidence and limitations.

## Read-only source inspection

On a Mac with an untouched official Claude Desktop 2.26454.2 installed:

    python3 scripts/inspect_2_26454_2.py --app /Applications/Claude.app

Optionally validate a language catalog you have the right to use:

    python3 scripts/inspect_2_26454_2.py \
      --app /Applications/Claude.app \
      --catalog-dir /path/to/your/catalog \
      --json

This command checks source signature, version and bundle identity, exact
SHA-256 target fingerprints, rewrite anchors, rewritten JS syntax, and
English-language catalog shape. With a user-provided catalog it also checks
coverage and ICU format arguments.

The command **does not** launch, rewrite, sign, install or modify an app.
Its report distinguishes static checks performed now from runtime evidence
recorded separately during validation.

## Verified validation milestones (2026-10-08)

1. Original signed app 2.26454.2 passed read-only preflight.
2. Mac branch tests: 294 tests OK (7 skipped), then 303 OK (7 skipped)
   after adding the candidate builder and extra safety regression tests.
3. A uniquely named app was built from the 2.26454.2 original,
   using a privately supplied Chinese language catalog, and re-signed ad-hoc.
4. Post-build verification passed: nested/outer signature, locale files and
   catalog integrity. The Gatekeeper assessment was rejected (expected).
5. The user confirmed the new app launches, the Chinese locale can be selected,
   its interface renders Chinese, and the choice persists after restart.
6. The user observed two successful "ok" responses from the existing
   DeepSeek V4.1 Flash Gateway connection.

This validates **only the observed tested environment**. The Mac had SIP
disabled before the tests; no SIP-on or Intel test was performed. Gateway
settings and other profile state may be shared by Claude app copies.
Keychain, sign-in and native integrations were not independently verified.

## Standard installation after promotion

The temporary candidate-only builder was removed from this branch because
the version is now declared in SUPPORTED_VERSIONS. After final regression
testing and a reviewed merge, the standard version-checked CLI will accept
official 2.26454.2 sources.

Do not overwrite existing localized app copies: the standard installer
refuses already-existing output paths.

Do not disable SIP or Gatekeeper to make the output run.
No Anthropic app, proprietary translation, gateway credentials or modified
JavaScript is redistributed.
