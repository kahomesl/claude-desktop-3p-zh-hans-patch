# Compatibility matrix

The installable versions are defined in code, in
[`src/claude_zh_patch/compat.py`](../src/claude_zh_patch/compat.py). This page
explains what the entries mean and what is required to add one.

## Installable

A version is installable only when it appears in `SUPPORTED_VERSIONS`.

| Version | Status | Verified on |
| --- | --- | --- |
| `2.26454.0` | **Runtime-verified** | macOS 26.5.2, Apple Silicon, SIP disabled |

### `2.26454.0` — the reference build

This is the only build that may be installed, and the only one that has been
run. Verified at runtime:

| Check | Result |
| --- | --- |
| Three rewrite sites matched with the expected occurrence counts | pass |
| Bundle re-signed ad-hoc, deep verification | pass |
| Restricted entitlements removed | pass |
| Interface renders in Simplified Chinese | pass |
| Language picker offers the locale | pass |
| Conversation through a third-party gateway | pass |
| Locale choice survives a restart | pass |

Environment, stated plainly because it bounds the claim: macOS 26.5.2 (25F84) on
Apple Silicon, **System Integrity Protection disabled**, and a copy created
locally so it carries no quarantine attribute. `spctl` reports the resulting copy
as *rejected*. Nothing here was verified on a machine with SIP enabled, on Intel,
or on any other macOS release.

## Examined but not installable

These builds have been inspected statically. They are deliberately **not
installable**: no runtime verification has been carried out.

| Version | Status |
| --- | --- |
| `2.26454.2` | **Not installable** — static inspection only |

### Why `2.26454.2` is interesting but still refused

Static inspection of the published `2.26454.2` build found the three files this
tool rewrites to be **byte-for-byte identical** to the reference build:

| File | sha256 |
| --- | --- |
| `shared-2-DgffKyBW.js` | `d5e17aa1e80c60af3784988242e1c673308c5746bfdb45a1c8b449da17f6effb` |
| `c49da61a8-BM3hC-jO.js` | `b54dfa935ab39b7a7f4de79b3a2e5a0ecb985a0ae8ad0697274e0bf903f719f6` |
| `shared-25-C8tkIaeS.js` | `738b690f0637bc20727bfe70341307cb4712b61cdaa830c1b322f1bdbe7b5f9e` |

Every anchor also matched its expected occurrence count. So the code paths this
tool touches are unchanged, and the structural risk is low.

That is still not the same as having run it. Nothing is known about whether this
build starts after re-signing, whether the interface renders, whether the locale
survives a restart, or whether an existing configuration still works. A
structural match is evidence, not a result.

**Consequence:** the installer refuses `2.26454.2` with exit code 3. If your
installed application has already been updated to it, install from a copy of
`2.26454.0` instead — see
[installing from a backup](INSTALL.md#installing-from-a-backup).

## Refusal behaviour

| Situation | Result |
| --- | --- |
| Version not in `SUPPORTED_VERSIONS` | Refused, exit code 3 |
| Unexpected number of anchor occurrences | Refused, exit code 5 |
| An allowlist sequence found outside a known anchor site | Refused, exit code 5 |
| A rewrite target's digest differs from the recorded one | Refused, exit code 5 |
| Bundle already carries a zh-Hans catalog | Refused, exit code 5 |
| Source bundle signature does not verify | Refused, exit code 5 |

There is **no flag that bypasses the version check**. This is enforced by the
command line parser and asserted by the test suite
(`tests/test_compat.py::NoBypassFlagTests`).

The format-argument check is also not bypassable. A difference the user would see
is refused outright, and a difference explained by a removed plural/select branch
is accepted automatically without a flag, so no acceptance flag exists for either
case. That too is asserted by `NoBypassFlagTests`.

## Adding support for a new version

Do not edit the version string and hope. Work through all of the following, and
commit the result together with the digests.

1. **Read the anchors.** Confirm every entry in `ANCHORS` still occurs exactly
   `occurrences` times in the recorded file, and nowhere else in the asset tree.
   If a file name or a needle changed, the patch strategy may need rethinking
   rather than re-pointing.

2. **Record digests.** Compute sha256 for each file in `PATCHED_FILENAMES` and
   put them in the `VersionInfo` entry.

3. **Check JavaScript compatibility.** Run the rewritten bundles through a parser
   (`node --input-type=module --check`). A lexical replacement can still produce
   invalid syntax.

4. **Check coverage.** Run `./zh-patch check --app <build> --catalog-dir <catalog>`
   and confirm the base coverage figure is acceptable for that build.

5. **Install and verify the signature.** `./zh-patch apply`, then
   `codesign --verify --deep --strict` on the result.

6. **Verify no restricted entitlement survives.** Inspect the copy's
   entitlements and confirm none of `com.apple.application-identifier`,
   `com.apple.developer.*`, or `keychain-access-groups` is present.

7. **Launch and confirm the interface.** Start the copy, choose the locale, and
   confirm the interface renders in it.

8. **Confirm a gateway conversation completes**, if you use one, and that a
   restart preserves the locale.

9. **Confirm the native features you care about.** Test sign-in and any native
   integration you rely on, and write down what you found — including what you
   found to be broken.

10. **Record the environment.** macOS version, architecture, SIP status, and
    whether the copy was quarantined. A new row in the tables above needs all
    four, because the answer differs between them.

Then add the version to `SUPPORTED_VERSIONS` with `runtime_verified=True` and a
`verified_environment` string that states what you actually tested.

If you can only complete the static steps, the honest outcome is an entry in
`ANCHOR_ONLY_VERSIONS` with the version still excluded from the installable
list. That is a useful contribution too.
