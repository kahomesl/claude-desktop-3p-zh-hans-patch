# Claude Desktop 2.26454.2 adaptation — validation in progress

**Status: NOT INSTALLABLE.** This is a candidate verification worksheet, not
a support announcement or a stable release. The production tool continues to
refuse version 2.26454.2 with exit code 3.

## Evidence available before this branch

Inspection of the official 2.26454.2 application reported that all three JS
rewrite targets had the same SHA-256 values as the runtime-verified 2.26454.0
reference. That evidence is recorded in [COMPATIBILITY.md](COMPATIBILITY.md).
Identical target JS does **not** establish that the rest of Electron, the 3P
runtime, signing, Gatekeeper and native integrations still work.

## Step A — read-only validation on an actual Mac

Run from the checkout on a Mac with an **unmodified, officially signed** copy
of Claude Desktop 2.26454.2:

    python3 scripts/inspect_2_26454_2.py --app /Applications/Claude.app

If you have a catalog that you are entitled to use:

    python3 scripts/inspect_2_26454_2.py \
      --app /Applications/Claude.app \
      --catalog-dir /path/to/your/catalog \
      --json

The script is deliberately read-only. It checks:

1. Version is exactly 2.26454.2 and the bundle identifier is unchanged.
2. The source code signature verifies strictly, and there is no existing
   Chinese catalog in the source.
3. Three rewrite-target hashes match recorded reference fingerprints.
4. All replacement anchors have exact expected occurrence counts,
   with no stray copies of the locale allowlist.
5. Three in-memory rewritten JS modules pass Node's ESM syntax checker.
6. Original English base and dynamic catalogs are readable.
7. If provided, the user-authorized translation catalog passes strict coverage
   and ICU placeholder checks (with legitimate removed-branch collapses).

No JS sources, app bundles, signing entitlements or user preferences are
modified. It does **not** produce an installable app.

### Interpreting the result

- STRUCTURAL PASS means only the static gates passed.
- Missing Node.js or any failed anchor/hash/signature/catalog check is not a pass.
- JSON fields runtimeVerified and installable are always false on success.
- Do not announce 2.26454.2 support on this evidence alone.

## Step B — isolated runtime validation (not yet performed)

Once Step A passes, this adaptation branch has a dedicated candidate builder.
It temporarily registers the exact fingerprinted version only within its own
Python process; the public CLI remains unchanged. Run with the real user-owned
catalog directory (do not upload it to GitHub):

    python3 scripts/build_candidate_2_26454_2.py \\
      --app /Applications/Claude.app \\
      --catalog-dir /path/to/your/catalog \\
      --target /Applications/Claude-3P-ZH-2.26454.2.app

The builder refuses any existing target and any output name other than
Claude-3P-ZH-2.26454.2.app, and statically verifies its new copy.
Do not overwrite the old Chinese app or expose a candidate as a stable release. Keep the existing 2.26454.0 Chinese copy untouched. Test 2.26454.2
from a fresh officially signed source into a **new, uniquely named target app**.
Never replace the existing Claude.app or Claude-3P-ZH.app.

Record these separate observations:

- Copy/rewrite/install runs to completion; source unchanged.
- Nested and outer ad-hoc signatures verify; restricted identity entitlements
  removed.
- The actual new copy starts without a codesigning failure.
- Language picker offers Simplified Chinese and UI renders it.
- A real request through CC Switch / 3P gateway completes.
- Quitting and restarting retains the locale.
- Native features used by the tester have documented outcomes, including
  any Keychain or login limitations.
- macOS build number, CPU architecture, SIP, quarantine and spctl results
  are recorded.

These are runtime tests on a Mac. No GitHub Actions or Linux unit test can
substitute for them.

## Step C — criteria for promotion

Only after Step B passes and evidence is reviewed:

1. Add 2.26454.2 to SUPPORTED_VERSIONS with verified fingerprints and an
   accurately scoped verified_environment.
2. Remove 2.26454.2 from ANCHOR_ONLY_VERSIONS.
3. Update version-gate tests and compatibility documentation without weakening
   any fail-closed safeguards.
4. Retain explicit SIP-on disclaimers if that environment remains untested.
5. Run unit tests, real-bundle integration suite, security scan, disclosure
   checks and isolated live launch.
6. Submit a reviewed PR before any stable or compatibility release claim.

**Do not disable SIP or Gatekeeper for this test.** An ad-hoc signed app may
lose team-scoped Keychain and other native capabilities.
