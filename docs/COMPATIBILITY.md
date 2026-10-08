# Compatibility matrix

The installable versions are defined in
[src/claude_zh_patch/compat.py](../src/claude_zh_patch/compat.py).
The allowlist is exact-version AND exact-file-hash gated. No unknown or
unvalidated build can be patched by using a command-line override.

## Runtime-verified, installable builds

| Claude Desktop version | Status | Verified environment |
| --- | --- | --- |
| 2.26454.0 | **Runtime-verified** | macOS 26.5.2 (25F84), Apple Silicon, SIP disabled |
| 2.26454.2 | **Runtime-verified** | macOS 26.5.2 (25F84), Apple Silicon, SIP disabled |

Both rows refer to **one verification Mac**, not independent test coverage.
The output is locally generated and ad-hoc signed, with no quarantine attribute.
The modified copy is rejected by the Gatekeeper spctl assessment. **Compatibility
on SIP-enabled Macs is unknown, and disabling SIP is not recommended.**

### 2.26454.0 — original reference

Runtime-confirmed: full application launch, Simplified Chinese language picker,
Chinese UI rendering, a completed third-party Gateway conversation, and locale
persistence across a restart.

### 2.26454.2 — runtime-tested extension (2026-10-08)

The following evidence comes from the user's actual Mac, with a signed
unmodified 2.26454.2 as source and a new, separately named output app.

| Check | Result / scope |
| --- | --- |
| Original app code signature | pass |
| Exact-version, Bundle ID and three target file hashes | pass |
| Three rewrite anchor locations, whole-tree allowlist count | pass |
| Rewritten JavaScript Node ESM syntax checks | pass |
| English base/dynamic catalog | 33,600 / 49 messages |
| Chinese catalog shape, ICU format and coverage | pass; 11 accepted removed-branch collapses |
| Isolated app build and ad-hoc signature verification | pass |
| Gatekeeper spctl assessment of generated app | rejected; expected for ad-hoc signature |
| Candidate opens without a reported crash | pass |
| Chinese locale in picker; interface renders in Chinese | pass |
| Quit/restart retains Chinese locale | pass |
| Existing Gateway model selector lists DeepSeek V4.1 Flash | observed |
| DeepSeek Gateway request and reply | two separate prompts received "ok" |
| SIP enabled, Intel, other macOS releases | **not tested** |
| Keychain, sign-in, system/native integrations, full profile isolation | **not tested** |

**Limitations of the evidence:** The app was built on a machine with SIP already
disabled; its working Gateway settings were already configured and may be shared
with other Claude app copies. Being a separately named .app does **not** imply
isolated account settings or user-profile storage. A screenshot of two successful
Gateway replies does not establish reliability of every model or native
integration. This localization tool does not itself enable third-party Gateway
connections.

### Exact structural fingerprints for both builds

Static inspection confirmed that the three modified JS files in 2.26454.0
and 2.26454.2 were byte-identical. These are SHA-256 fingerprints, not
proprietary file contents.

| File | SHA-256 |
| --- | --- |
| shared-2-DgffKyBW.js | d5e17aa1e80c60af3784988242e1c673308c5746bfdb45a1c8b449da17f6effb |
| c49da61a8-BM3hC-jO.js | b54dfa935ab39b7a7f4de79b3a2e5a0ecb985a0ae8ad0697274e0bf903f719f6 |
| shared-25-C8tkIaeS.js | 738b690f0637bc20727bfe70341307cb4712b61cdaa830c1b322f1bdbe7b5f9e |

## Other builds: not installable

No other application versions have been runtime verified. A changed version
remains blocked even when one or two anchors happen to match. Do not bypass
the version check or guess the release's internal layout.

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
