# Security

## Reporting a problem

Open a private security advisory through the repository's **Security** tab
("Report a vulnerability"). If that is unavailable, open a normal issue that
describes the *class* of problem without including a working exploit, and ask for
a private channel.

Please do not include real credentials, tokens, account identifiers, or personal
data in a report. A description of the pattern is enough.

There is no bug bounty. This is a small, unofficial project and responses are
best-effort.

## What this tool does not touch

| | |
| --- | --- |
| The installed application | Never written to. Only read, and copied. |
| `~/Library/Application Support` | Never read, never written. |
| Credentials | Never read. No command requests or stores an API key, token, or cookie. |
| The network | No command opens a connection. All operations are local. |
| SIP and Gatekeeper | Never modified, and no documentation asks you to modify them. |

The tool's only elevated requirement is write access to `/Applications` when it
installs the copy there, which is the same access any application installer needs.

## Static scan

The repository ships its own scanner and runs it over itself.

```bash
./zh-patch scan .
```

It looks for two classes of problem.

**Credentials and personal data.** API keys by vendor prefix, private key blocks,
bearer tokens, assigned secret-looking values, session cookies, home-directory
paths, e-mail addresses, and chat-transcript-shaped content.

Findings never echo the matched value — only its length and a short masked
prefix — so running the scanner cannot leak a secret into a log or a terminal
scrollback. Add `security-scan:allow` to a line to suppress findings on it, with
a comment saying why.

**Third-party material.** Application bundles, Electron archives, provisioning
profiles, key material, certificates, compiled libraries, and extracted
translation catalogs — meaning any JSON file with a large number of top-level
entries, which is what a message catalog looks like.

The test suite asserts that a scan of the repository returns nothing, so the scan
cannot silently rot:

```bash
python3 -m unittest tests.test_security_scan -v
```

## How the tool is written to avoid introducing problems

- **No shell interpolation.** External commands are invoked as argument lists.
  No user-supplied value is ever concatenated into a command string.
- **No `eval`, no `exec`.** The JavaScript rewriting is literal byte replacement
  at positions that are verified to occur exactly once.
- **No network client** anywhere in the package.
- **Path containment.** Catalog file references must be relative and may not
  traverse out of the catalog directory.
- **Refusal over guessing.** Unexpected structure stops the operation with a
  non-zero exit code rather than proceeding on an assumption.
- **Cleanup on failure.** A partially created copy is removed. The source bundle
  is never modified at any point.

## What the installation changes about your security posture

Worth stating plainly, because "the tool does not do anything dangerous" and "the
result is as safe as the original" are different claims.

The installed copy:

- carries an ad-hoc signature instead of the publisher's Developer ID;
- reports as *rejected* to `spctl`;
- is **not** notarised, so its contents have not been checked by Apple;
- does not carry the team-scoped keychain access groups, and therefore cannot
  reach credentials the original stored under them.

In exchange, the copy is a local artifact that you built from a bundle you
already had, and every change it contains is described in
[`INSTALL.md`](INSTALL.md) and recorded in the marker file inside it.

The correct response to a Gatekeeper block on such a copy is **not** to disable
Gatekeeper. It is to check why the copy is quarantined — see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## Dependencies

None. The tool uses only the Python standard library and the macOS system
utilities `codesign`, `spctl`, `ditto`, and optionally `node`.

## Supported versions

Only the Python version in `pyproject.toml` and the application versions in
[`COMPATIBILITY.md`](COMPATIBILITY.md) are supported. Security fixes are applied
to the current release only.
