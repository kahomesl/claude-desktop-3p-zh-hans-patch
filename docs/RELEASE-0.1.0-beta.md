# v0.1.0-beta — Claude Desktop 2.26454.2 compatibility

**Pre-release of the unofficial macOS Simplified Chinese localization tool.**

## Changes

- Official Claude Desktop **2.26454.2** is now in the exact-version and SHA-256-fingerprinted compatibility allowlist.
- Previously supported **2.26454.0** remains supported.
- An official signed 2.26454.2 was inspected, patched into a separate app, re-signed ad-hoc and verified on one Apple Silicon Mac.
- Runtime checks confirmed launch, Simplified Chinese language selection, Chinese UI, restart persistence, and two successful `ok` replies from an existing DeepSeek Gateway configuration.
- Strict refusal continues for all unknown or structurally different app versions; no unsafe override flags were introduced.
- Tests and bilingual compatibility documentation have been updated.

## Important limitations

- **Only tested on macOS 26.5.2 (25F84), Apple Silicon, with SIP already disabled.** Compatibility with **SIP enabled** is unknown. Do not disable SIP or Gatekeeper to try this tool.
- Generated apps are **ad-hoc signed**; Gatekeeper rejects them. This is not an official Apple notarized distribution.
- Keychain access, sign-in, native integrations, Intel Macs, other macOS builds and independent app-profile isolation have not been verified.
- Gateway compatibility in the test used an **already configured** gateway; this tool does not configure CC Switch or DeepSeek.
- The project **does not ship** Claude.app, altered Anthropic JavaScript or Chinese translation data. Supply your own authorized catalog with `--catalog-dir`.

## Install and verify

Follow the [installation guide](../docs/INSTALL.md) or [中文安装指南](../docs/INSTALL.zh-Hans.md).

Run `./zh-patch check --app /Applications/Claude.app --catalog-dir /path/to/your/catalog` before applying to a separate, nonexistent target path. Never overwrite your official app or an existing localized copy.

Compatibility evidence: [docs/COMPATIBILITY.md](../docs/COMPATIBILITY.md).

This is **Pre-release**, not a general-availability or universally compatible stable version.
