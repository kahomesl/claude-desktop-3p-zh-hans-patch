# claude-desktop-3p-zh-hans-patch

Install a Simplified Chinese interface into a **local copy** of Claude Desktop
for macOS, without touching the application you already have.

This is an **unofficial community tool**. It is **not affiliated** with
Anthropic in any way.

---

## Read this first

Four things about this project are unusual, and all four matter.

**1. It ships no translation data.** There is **no Chinese translation resource
in this repository** — no message catalog, no extracted text, and no code that
downloads or extracts any. You must supply your own catalog with `--catalog-dir`,
and you are responsible for having the right to use it. Until you do, the tool
cannot install anything.

**2. It refuses to run on unverified builds.** Only the application versions
listed in [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) are installable.
There is no override flag — not because one was forgotten, but because patching
a build whose internal structure has not been checked is how you get a broken
application and a confusing bug report.

**3. It has been verified on one Mac only, with SIP disabled — and compatibility
with SIP enabled is unconfirmed.** The single verification environment ran with
System Integrity Protection turned off, which is not the default on macOS. No
SIP-enabled Mac has been tested, so whether the result works there is unknown.
Passing the checks in this repository is **not a guarantee** that the interface
renders correctly, that sign-in works, or that any particular Mac can run the
result. See [Verified environment](#verified-environment) below.

**4. The result is ad-hoc signed.** Editing an application invalidates its
signature, so the copy is re-signed without a Developer ID. That has real
consequences, described in [What changes](#what-changes).

---

## What it does

1. Copies your installed Claude Desktop to a separate bundle
   (`/Applications/Claude-3P-ZH.app` by default).
2. Rewrites three JavaScript assets so the language picker offers
   `zh-Hans` and accepts it.
3. Writes the language resource you supplied into the copy's `i18n` directory.
4. Re-signs the copy ad-hoc, **removing the restricted entitlements an ad-hoc
   signature cannot carry** (see [Signing](#signing-and-entitlements)).
5. Verifies the result and records what it did in a marker file inside the copy.

Your installed application is never modified. Neither is your user data, your
third-party gateway configuration, or your model-switching tooling.

## What it does not do

- It does not modify `/Applications/Claude.app`.
- It does not touch `~/Library/Application Support`.
- It does not read, store, or transmit credentials, tokens, or chat history.
- It does not disable System Integrity Protection or Gatekeeper, and it does not
  ask you to.
- It does not redistribute Anthropic's application, code, or translations.

---

## Requirements

| | |
| --- | --- |
| Operating system | macOS on Apple Silicon (verified) or Intel (unverified) |
| Python | 3.9 or newer — the system `python3` is enough |
| Application | An installable version, from [the compatibility matrix](docs/COMPATIBILITY.md) |
| Language resource | A catalog directory you prepared and have the right to use |
| Disk | Roughly twice the size of the application, plus the copy |

`node` is optional. When present, the rewritten JavaScript is syntax-checked
before installation.

`./zh-patch` runs straight from a checkout and needs nothing installed. The
optional `pip install` path needs a reasonably current `pip` (22 or newer): the
`pip` bundled with the Command Line Tools Python is old enough to misread modern
package metadata and will produce a wheel named `UNKNOWN`. See
[installing the command](docs/INSTALL.md#installing-the-command-instead).

Install the supported application version first. If your installed version has
since been updated, keep a copy of a supported build and point the tool at it
with `--app` — see [installing from a backup](docs/INSTALL.md#installing-from-a-backup).

---

## One-click install

If you would rather not use a terminal, double-click **`启动Claude中文版.command`**
in the repository folder.

On the first run it will:

1. open the macOS folder picker so you can select the language resource directory
   you prepared;
2. remember that choice in `~/.config/claude-zh-patch/config.json` — mode `600`,
   holding nothing but the two paths you chose;
3. run the same `check → apply → verify` the command line uses, printing progress
   in Chinese;
4. offer to start the Chinese copy.

After that, the same double-click verifies the existing copy and opens it.

It never asks for an administrator password, never disables SIP or Gatekeeper,
never terminates a process, and never overwrites an existing bundle — if one is
already at the target it is verified instead. The version allowlist, the ad-hoc
signing and the ICU validation are the same code the command line runs; the
launcher is a front end, not a second implementation.

The launcher needs a working Python 3.9 or newer, because it runs this project's
code. macOS no longer ships one; if yours is missing the launcher says so and
points you at `xcode-select --install`.

### macOS will probably block it the first time

A `.command` file that arrived by being **downloaded** carries a quarantine
attribute, and macOS refuses to run those. You may see a warning about an
unidentified developer, or nothing may appear to happen. That is ordinary macOS
behaviour for any downloaded script — and this project does **not** ask you to
turn Gatekeeper off to get past it.

Any of these avoids the problem:

- **Clone with `git`**, which does not set the quarantine attribute:

  ```bash
  git clone https://github.com/kahomesl/claude-desktop-3p-zh-hans-patch.git
  ```

- **Or skip the launcher** and use [Quick start](#quick-start) below, which does
  the same work from a terminal.
- If you downloaded a ZIP, you can clear the attribute yourself — but only after
  reading the script:

  ```bash
  xattr -d com.apple.quarantine 启动Claude中文版.command
  ```

The launcher is verified to the same extent as everything else here, which is the
single environment described in [Verified environment](#verified-environment):
macOS 26.5.2 on Apple Silicon with **SIP disabled**. **Compatibility with SIP
enabled is unconfirmed**, and no SIP-enabled Mac has been tested.

---

## Quick start

```bash
git clone https://github.com/kahomesl/claude-desktop-3p-zh-hans-patch.git
cd claude-desktop-3p-zh-hans-patch
```

Check the application and your language resource, writing nothing:

```bash
./zh-patch check --catalog-dir ~/my-catalog
```

Install, once `check` succeeds:

```bash
./zh-patch apply --catalog-dir ~/my-catalog
```

Verify the copy on disk:

```bash
./zh-patch verify
```

Undo, by moving the copy to the Trash:

```bash
./zh-patch rollback
```

Full walkthrough: [`docs/INSTALL.md`](docs/INSTALL.md).

---

## The language resource

This tool contains no Chinese text. To install anything you must produce a
catalog directory containing the messages, and you must have the right to use
them.

To see which keys the application expects:

```bash
./zh-patch keys --out my-catalog/base.json
```

That writes every required key with an empty value. It deliberately does **not**
export the application's English text — check the application you already have
installed if you need to read what a message says.

Then write a `catalog.json` manifest and fill in the values, and pass the
directory with `--catalog-dir`. The format, the validation rules, and what the
tool checks are documented in
[`docs/CATALOG-FORMAT.md`](docs/CATALOG-FORMAT.md); a starting point is in
[`templates/catalog/`](templates/catalog/).

The loader refuses a catalog that is malformed, under-covered, or that would
leave a visible hole in the interface. If it refuses, it names the offending keys
so you can fix them.

To see every problem in detail — including which arguments the application
supplies for each message and which your resource supplies — use `lint`:

```bash
./zh-patch lint --catalog-dir ~/my-catalog
./zh-patch lint --catalog-dir ~/my-catalog --report report.md
```

One case is accepted rather than refused, and it is worth knowing about. When the
application selects between arguments by count or by category, a language that
does not inflect omits some of those branches, and the argument only that branch
used goes with it. That is a correct translation, so it installs with no flag;
`lint` lists what was accepted and `apply` records the count in the install
marker. An argument the application renders *outside* every branch, or inside a
branch the translation kept, is a visible hole and is always refused. There is no
flag that overrides that.

> Supplying your own resource does not grant you any right to it, and passing
> these checks does not mean Anthropic has authorised anything. You are
> responsible for the text you install.

---

## What changes

| | |
| --- | --- |
| Your installed application | Unchanged |
| User data, gateway settings, switch tooling | Unchanged |
| The new copy's signature | **Ad-hoc**, replacing Anthropic's Developer ID |
| Gatekeeper | Reports the copy as rejected (see below) |
| Keychain and native features | **May behave differently** |

### Signing and entitlements

The original build carries entitlements that only mean something to code whose
identity is backed by a provisioning profile — `com.apple.application-identifier`,
`com.apple.developer.team-identifier`, and team-scoped `keychain-access-groups`.
An ad-hoc signature cannot substantiate any of them. This tool removes them and
adds `com.apple.security.cs.disable-library-validation` in their place, which is
what an ad-hoc signed Electron bundle needs in order to load its own frameworks.

The practical consequences:

- **Keychain**: anything the application stores under its team-scoped keychain
  access groups is no longer reachable by the copy. Expect to sign in again, and
  expect the copy not to share stored credentials with the original.
- **Native integrations**: features that depend on the code signature — some
  permissions, some helpers, some system integrations — may not work.
- **Gatekeeper**: the copy is not notarised and not Developer ID signed, so
  `spctl` rejects it. A copy **created locally by this tool** carries no
  quarantine attribute and therefore starts normally; a copy that has been
  downloaded, archived, or transferred will be quarantined and Gatekeeper will
  block it.

> Do not disable System Integrity Protection or Gatekeeper globally to work
> around this. That is a system-wide reduction in security for a single
> application's convenience. If a locally created copy will not start, report it
> — see [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

### Verified environment

Both supported builds were tested on the same Mac:

| | |
| --- | --- |
| macOS | 26.5.2 (25F84) |
| Architecture | Apple Silicon (arm64) |
| Claude Desktop | 2.26454.0 and 2.26454.2 |
| System Integrity Protection | **disabled on the verification machine** |
| Gatekeeper assessment of the copy | `spctl` reported *rejected* |
| Copy origin | created locally, so not quarantined |

Runtime verification for both exact builds includes Chinese UI and language
picker rendering, and persistence after restart. On 2.26454.2, a configured
DeepSeek Gateway successfully returned two separate "ok" replies. Gateway
configuration is not supplied by this tool; Keychain and native integration
behavior have not been verified.

> **Compatibility with SIP enabled is unconfirmed.** System Integrity Protection
> was **disabled** on the verification machine, which is not how macOS ships by
> default. No Mac with SIP enabled has been tested. The tool does not require you
> to disable SIP, and you should not disable it — but whether the result works
> with SIP on is simply not known.

**Not verified:** SIP enabled, Intel, other macOS versions, application builds
outside the two pinned versions, Keychain behavior, native integrations,
independent user-profile isolation, or reliability across other Gateway models. "It works on the machine it was tested
on" is not the same claim as "it works on your Mac".

---

## Commands

| Command | Purpose |
| --- | --- |
| `check` | Assess the application and optionally a catalog. Writes nothing. |
| `apply` | Create the localised, re-signed copy. |
| `verify` | Re-check an installed copy. Static checks only. |
| `rollback` | Move an installed copy to the Trash. Reversible. |
| `lint` | Report every problem in a language resource, in detail. Writes nothing. |
| `keys` | List the message keys the application expects, with empty values. |
| `scan` | Static scan for secrets and third-party material. |
| `version` | Tool version and compatibility table. |

Add `--json` anywhere for machine-readable output.

The double-clickable launcher above is a front end for these same commands, not a
replacement: `启动Claude中文版.command` calls `check`, `apply` and `verify` in
turn and does nothing else.

Exit codes: `0` success, `1` error, `2` usage, `3` unsupported application
version, `4` language resource rejected, `5` bundle structure not recognised.

---

## Security and privacy

- **Offline.** No command makes a network request.
- **No credentials.** Nothing in this repository contains or asks for an API
  key, token, cookie, or account identifier, and the tool never reads them.
- **No user data.** `~/Library/Application Support` is not read or written.
- **No third-party material.** The repository contains no application binaries,
  no modified JavaScript, and no extracted translation catalog.
- **Scanned.** `./zh-patch scan .` runs the repository's own scanner over it;
  the test suite asserts a clean result.

To report a security problem, see [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Licence and trademarks

Original code and documentation: **Apache License 2.0** —
see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

The licence covers this project's own work only. It does not cover Claude,
Claude Desktop, any Anthropic resource, or any translation. "Claude" and
"Anthropic" are trademarks of Anthropic PBC, used descriptively to state what
this tool interoperates with. See [`docs/DISCLAIMER.md`](docs/DISCLAIMER.md).

---

## Documentation

| | |
| --- | --- |
| [Install guide](docs/INSTALL.md) · [安装指南](docs/INSTALL.zh-Hans.md) | Step by step, including installing from a backup |
| [Compatibility matrix](docs/COMPATIBILITY.md) | Which builds are installable, and what verifying a new one requires |
| [Language resource format](docs/CATALOG-FORMAT.md) | Manifest, schemas, validation rules |
| [Troubleshooting](docs/TROUBLESHOOTING.md) · [故障排查](docs/TROUBLESHOOTING.zh-Hans.md) | What to do when something does not work |
| [Disclaimer](docs/DISCLAIMER.md) | The full statement of limitations |
| [Security](docs/SECURITY.md) | What is scanned and how to report a problem |
| [Contributing](CONTRIBUTING.md) | Including how to add support for a new version |
| [Changelog](CHANGELOG.md) | Release history |

中文文档见 [`README.zh-Hans.md`](README.zh-Hans.md)。

---

## Contributing

Adding support for a new application version means running the full verification
procedure and committing the result — the checks are listed in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md). Fixing a dropped format
argument in a language resource is a good first contribution. See
[`CONTRIBUTING.md`](CONTRIBUTING.md).
